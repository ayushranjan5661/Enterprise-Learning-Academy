"""FastAPI app: routes + static frontend.

Run from the project root:
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from backend import config, cost_tracker, orchestrator, pdf_export, storage
from backend.rag import chroma_store
from backend.schemas import CreateProgrammeRequest, ProgrammeState, RejectRequest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("api")

@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_dirs()
    if config.missing_api_key():
        log.warning("MISTRAL_API_KEY is not set — agent calls will fail.")

    # Hosts with an ephemeral filesystem discard the persisted Chroma store on every
    # restart, which would leave every agent running without retrieval. Rebuild it here
    # rather than failing silently. Never fatal: a degraded RAG beats a dead service.
    if config.SEED_ON_BOOT and not config.missing_api_key() and chroma_store.count() == 0:
        log.info("vector store empty and SEED_ON_BOOT set — seeding sample materials...")
        try:
            from backend.rag import seed_content

            seed_content.main()
        except Exception:
            log.exception("boot seed failed — continuing with an empty vector store")

    log.info("vector store: %s chunk(s) at %s", chroma_store.count(), config.CHROMA_PERSIST_DIR)
    yield


app = FastAPI(
    title="AI Learning Academy — Multi-Agent System",
    version="1.0.0",
    description="Specialised agents design, populate, assess and quality-gate an "
    "AI-upskilling programme.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- health / meta
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "api_key_configured": not config.missing_api_key(),
        "models": {
            "large": config.LLM_MODEL_LARGE,
            "small": config.LLM_MODEL_SMALL,
            "embed": config.EMBED_MODEL,
        },
        "vector_store": {
            "collection": config.COLLECTION_NAME,
            "chunks": chroma_store.count(),
            "path": str(config.CHROMA_PERSIST_DIR),
        },
        "max_revisions": config.MAX_REVISIONS,
        "max_human_rejections": config.MAX_HUMAN_REJECTIONS,
    }


@app.get("/api/programmes")
def list_programmes(limit: int = 25) -> dict:
    return {"runs": storage.list_runs(limit)}


# ---------------------------------------------------------------- run lifecycle
def _require(run_id: str) -> ProgrammeState:
    state = storage.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
    return state


@app.post("/api/programmes", status_code=202)
def create_programme(body: CreateProgrammeRequest, background: BackgroundTasks) -> dict:
    if config.missing_api_key():
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")

    state = orchestrator.start_run(body.manager_request)
    # Background so the frontend can poll and watch each agent complete.
    background.add_task(orchestrator.orchestrate, state)
    return {"run_id": state.run_id, "status": state.status}


@app.get("/api/programmes/{run_id}")
def get_programme(run_id: str) -> dict:
    state = _require(run_id)
    return {
        **state.model_dump(exclude={"history", "cost_log"}),
        "cost_total": cost_tracker.summarise(state.cost_log)["total"],
        "max_revisions": config.MAX_REVISIONS,
        "max_human_rejections": config.MAX_HUMAN_REJECTIONS,
        "history_length": len(state.history),
    }


@app.get("/api/programmes/{run_id}/history")
def get_history(run_id: str) -> dict:
    state = _require(run_id)
    return {"run_id": run_id, "history": state.history}


@app.get("/api/programmes/{run_id}/cost")
def get_cost(run_id: str) -> dict:
    state = _require(run_id)
    return {"run_id": run_id, **cost_tracker.summarise(state.cost_log)}


@app.get("/api/programmes/{run_id}/export/{section}.pdf")
def export_pdf(run_id: str, section: str) -> Response:
    """Download curriculum / content_plan / assessments as a PDF."""
    state = _require(run_id)

    entry = pdf_export.EXPORTS.get(section)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown section '{section}' — expected one of {sorted(pdf_export.EXPORTS)}",
        )
    attr, build = entry
    if not getattr(state, attr, None):
        raise HTTPException(
            status_code=409,
            detail=f"run has no {section} yet (status '{state.status}') — nothing to export",
        )

    try:
        pdf = build(state)
    except Exception as exc:  # a render failure must not read as a missing run
        log.exception("PDF render failed for %s/%s", run_id, section)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    filename = f"{section}_{run_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf)),
        },
    )


@app.post("/api/programmes/{run_id}/approve")
def approve(run_id: str) -> dict:
    state = _require(run_id)
    if state.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"run is '{state.status}' — only 'awaiting_approval' can be approved",
        )
    state.status = "approved"
    state.human_decision = "approved"
    storage.record(state, "human", "approved", "Human approved the final programme.")
    storage.save(state)
    return {"run_id": run_id, "status": state.status}


@app.post("/api/programmes/{run_id}/reject")
def reject(run_id: str, body: RejectRequest, background: BackgroundTasks) -> dict:
    state = _require(run_id)
    if state.status not in ("awaiting_approval", "approved"):
        raise HTTPException(
            status_code=409,
            detail=f"run is '{state.status}' — nothing to reject yet",
        )
    if state.human_revision_count >= config.MAX_HUMAN_REJECTIONS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"human rejection cap reached ({config.MAX_HUMAN_REJECTIONS}) — "
                "this brief needs a manual redesign, not another automated pass"
            ),
        )
    # Flip the status synchronously so a poll landing before the background task starts
    # doesn't briefly re-show the approval gate.
    state.status = "revising"
    storage.save(state)
    background.add_task(
        orchestrator.resume_after_human_rejection, state, body.feedback, body.target_agent
    )
    return {"run_id": run_id, "status": "revising", "routed_to": body.target_agent or "curriculum"}


# ---------------------------------------------------------------- frontend
if config.FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(config.FRONTEND_DIR / "index.html"))

else:  # pragma: no cover

    @app.get("/", include_in_schema=False)
    def index_missing() -> RedirectResponse:
        return RedirectResponse("/docs")
