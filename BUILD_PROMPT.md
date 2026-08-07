# Build Prompt — AI Learning Academy (Multi-Agent System)

> Paste this whole document into your coding assistant (Claude Code, Cursor, etc.) as the build instruction.

## 1. What to build

A multi-agent system where specialized AI agents collaborate — and challenge each other — to design, deliver, and quality-check a corporate AI-upskilling programme.

**Trigger input example:**
> "Create an AI upskilling programme for 1,000 software engineers across India, covering GenAI, RAG, AI agents and responsible AI."

**Pipeline:**
```
Manager Request
     │
     ▼
 Orchestrator
     │
     ▼
Learner Analysis Agent → Curriculum Agent → Content Agent → Assessment Agent → Quality Agent
     ▲                                                                              │
     └──────────────── REJECTED (feedback + target agent) ◄───────────────────────┘
                                    │
                              APPROVED
                                    │
                                    ▼
                        Orchestrator → Human Approval → Final Programme
```

## 2. Tech stack (mandatory)

- **LLM provider:** Mistral AI — use the official `mistralai` Python SDK.
  - Reasoning/generation model: `mistral-large-latest`
  - Cheap/simple tasks: `mistral-small-latest`
  - Embeddings: `mistral-embed`
  - *(Verify current model IDs against Mistral's docs — aliases like `-latest` auto-resolve, don't hardcode dated snapshots.)*
- **Backend:** FastAPI (Python), `uvicorn` for serving.
- **Vector store:** ChromaDB (local persistent client), used by the Content Agent for RAG over the learning-materials library.
- **Frontend:** Plain HTML/CSS/JS (no framework) — talks to the backend only via `fetch()`.
- **State/storage:** JSON files or SQLite for run history; in-memory dict is fine for the MVP.

## 3. Repository structure

```
enterprise_learning_academy/
  backend/
    main.py                  # FastAPI app, routes
    config.py                 # env vars: MISTRAL_API_KEY, model names, chroma path
    schemas.py                 # Pydantic models for every agent's input/output
    orchestrator.py             # pipeline + quality-gate loop + revision routing
    agents/
      base_agent.py            # shared call-Mistral + cost-log helper
      learner_analysis.py
      curriculum.py
      content.py                # queries ChromaDB
      assessment.py
      quality.py
    rag/
      chroma_store.py           # ChromaDB client, collection setup, upsert/query
      seed_content.py           # script to embed sample learning materials into Chroma
      sample_materials/          # markdown/text files to seed the vector store
    cost_tracker.py
    storage.py                  # persist run state (JSON/SQLite)
  frontend/
    index.html
    styles.css
    app.js
  data/
    chroma_db/                  # persisted ChromaDB (gitignored)
    runs/                       # persisted run JSON (gitignored)
  .env.example
  requirements.txt
  README.md
```

## 4. Data model (Pydantic, in `schemas.py`)

Define a single `ProgrammeState` object that flows through every agent — each agent reads what it needs and writes only its own section:

```python
class ProgrammeState(BaseModel):
    run_id: str
    manager_request: str
    learner_analysis: dict | None = None
    curriculum: dict | None = None
    content_plan: dict | None = None
    assessments: dict | None = None
    quality_review: dict | None = None
    status: str                    # "running" | "revising" | "awaiting_approval" | "approved" | "failed"
    revision_count: int = 0
    revision_feedback: list[str] = []
    revision_target: str | None = None   # which agent to re-run
    cost_log: list[dict] = []
    history: list[dict] = []       # every agent call, for audit/debugging
```

## 5. Agent specifications

Each agent is a Python function: `run(state: ProgrammeState) -> ProgrammeState`. Each calls Mistral's chat completion with a **JSON schema / structured output request** (use Mistral's JSON mode) so the orchestrator never has to regex-parse text.

| Agent | Model | Input it reads | Output it writes | Notes |
|---|---|---|---|---|
| **Learner Analysis** | `mistral-small-latest` | `manager_request` | `learner_analysis`: roles, skill levels, gaps, count, region | Pure extraction/classification task |
| **Curriculum** | `mistral-large-latest` | `learner_analysis` (+ `revision_feedback` if revising) | `curriculum`: modules, learning objectives, sequencing, duration | Needs real instructional-design judgment |
| **Content** | `mistral-small-latest` + ChromaDB | `curriculum` | `content_plan`: per-module recommended existing material (from Chroma RAG) + flagged **content gaps** where nothing relevant was found | Embed the query with `mistral-embed`, retrieve top-k from Chroma, ask the model to map results to modules and call out gaps |
| **Assessment** | `mistral-large-latest` | `curriculum`, `content_plan` | `assessments`: quizzes, coding exercises, practical rubrics per module | |
| **Quality/Evaluation** | `mistral-large-latest` | everything above | `quality_review`: `{"verdict": "approved"|"rejected", "issues": [...], "target_agent": "curriculum"|"content"|"assessment"|null}` | Must actively look for problems — prompt it to be adversarial, not agreeable. `target_agent` tells the orchestrator who owns the fix (conflict resolution) |
| **Orchestrator** | code, not an LLM call (routing logic only) | full state | drives the loop, applies revision cap, triggers human approval | |

## 6. RAG / ChromaDB spec

- One Chroma collection: `learning_materials`.
- Seed script (`seed_content.py`) embeds a handful of sample docs (GenAI intro, RAG basics, agent frameworks, responsible AI guidelines) using `mistral-embed`, stores them with metadata `{topic, format, level}`.
- Content Agent flow: for each curriculum module → embed the module's learning objective with `mistral-embed` → `collection.query(query_embeddings=..., n_results=3)` → pass results + module to the LLM → get back "use this material" or "GAP: nothing suitable found".

## 7. Orchestration logic (`orchestrator.py`)

```python
MAX_REVISIONS = 3

def run_pipeline(state):
    state = learner_analysis.run(state)
    state = curriculum.run(state)
    state = content.run(state)
    state = assessment.run(state)
    return state

def orchestrate(manager_request: str) -> ProgrammeState:
    state = ProgrammeState(run_id=new_id(), manager_request=manager_request, status="running")
    while True:
        state = run_pipeline(state)
        state = quality.run(state)
        if state.quality_review["verdict"] == "approved":
            state.status = "awaiting_approval"
            break
        if state.revision_count >= MAX_REVISIONS:
            state.status = "failed"      # failure recovery: escalate instead of looping forever
            break
        state.revision_count += 1
        state.revision_feedback = state.quality_review["issues"]
        state.revision_target = state.quality_review["target_agent"]
        # re-run only from the target agent onward, not the whole pipeline, once revision_target logic is added
    persist(state)
    return state
```

Start with "re-run whole pipeline on rejection" for simplicity, then upgrade to "re-run only from `revision_target` onward" as a stretch goal — that's the real conflict-resolution lesson.

## 8. FastAPI endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/programmes` | Submit manager request → kicks off orchestration (run sync for MVP, background task later) |
| `GET` | `/api/programmes/{run_id}` | Poll current state (status, latest agent output, cost so far) |
| `GET` | `/api/programmes/{run_id}/history` | Full agent-by-agent trace, for the "watch it work" view |
| `POST` | `/api/programmes/{run_id}/approve` | Human approval step — required before status becomes `approved` |
| `POST` | `/api/programmes/{run_id}/reject` | Human can also reject after seeing the draft, feeding back to the orchestrator |
| `GET` | `/api/programmes/{run_id}/cost` | Per-agent, per-revision token/cost breakdown |

## 9. Cost tracking

Every agent call logs to `state.cost_log`:
```python
{"agent": "curriculum", "model": "mistral-large-latest",
 "prompt_tokens": ..., "completion_tokens": ..., "revision": state.revision_count}
```
Sum and expose via `/cost`. Frontend should show a running cost total and a per-agent breakdown table — this is the "cost/token management" learning objective made visible.

## 10. Frontend requirements

- **Single page** (`index.html`): a textarea for the manager request + "Submit" button.
- **Progress view:** poll `/api/programmes/{run_id}` every 1–2s, render each agent's status as it completes (pending → running → done), show revision loops explicitly when they happen ("Quality Agent rejected — sending back to Curriculum Agent").
- **Final view:** rendered curriculum, content plan, assessments, quality verdict, cost summary, and an **Approve / Reject** button calling the approval endpoints.
- Keep it plain — no build step, no framework, just `fetch()` + DOM updates in `app.js`.

## 11. Failure recovery requirements

- Wrap every Mistral API call in try/except with retry (2 attempts, backoff).
- If an agent call fails after retries, mark `state.status = "failed"`, record the error in `history`, and surface it in the frontend rather than crashing the request.
- Revision loop must have a hard cap (`MAX_REVISIONS`) — never loop forever.

## 12. Environment / config

`.env.example`:
```
MISTRAL_API_KEY=your_key_here
CHROMA_PERSIST_DIR=./data/chroma_db
LLM_MODEL_LARGE=mistral-large-latest
LLM_MODEL_SMALL=mistral-small-latest
EMBED_MODEL=mistral-embed
MAX_REVISIONS=3
```

## 13. Build order (do this incrementally, verify each step runs before moving on)

1. FastAPI skeleton + `.env` loading + a health-check route.
2. `base_agent.py`: one helper that calls Mistral chat completion with JSON-schema output, logs cost. Test with a throwaway single call.
3. Learner Analysis agent alone, wired to `POST /api/programmes`, returning just that section.
4. ChromaDB seed script + Content Agent RAG query, tested standalone.
5. Chain all 5 agents into `run_pipeline` (no quality gate yet).
6. Add Quality Agent + the revision loop + `MAX_REVISIONS` cap.
7. Add cost tracking end-to-end + `/cost` endpoint.
8. Build the frontend: submit → poll → render → approve/reject.
9. Add failure recovery (retries, error states) last, once the happy path works.

---

Now scaffold the repository above and implement step 1.
