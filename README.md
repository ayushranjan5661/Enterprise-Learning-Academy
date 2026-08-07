# AI Learning Academy — Multi-Agent System

Five specialised AI agents collaborate — and challenge each other — to design a corporate
AI-upskilling programme from a single manager request. A Quality Agent adversarially
reviews the result and can **reject** it, routing the fix back to the agent that owns it.
Nothing is final until a human approves.

```
Manager Request
     │
     ▼
 Orchestrator  (routing logic only — not an LLM)
     │
     ▼
Learner Analysis → Curriculum → Content (RAG) → Assessment → Quality
     ▲                                                          │
     └────────── REJECTED (feedback + target agent) ◄───────────┘
                                │
                          APPROVED
                                │
                                ▼
              Orchestrator → Human Approval → Final Programme
```

## Stack

| Layer | Choice |
|---|---|
| LLM | Mistral AI (`mistralai` Python SDK) — `mistral-large-latest`, `mistral-small-latest`, `mistral-embed` |
| Backend | FastAPI + uvicorn |
| Vector store | ChromaDB, local persistent client |
| Frontend | Plain HTML/CSS/JS, `fetch()` only — no build step |
| Storage | In-memory dict + one JSON file per run under `data/runs/` |

## Setup

```powershell
# 1. dependencies (a venv named myenv already exists in this repo)
.\myenv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. configure — copy .env.example to .env and add your key
copy .env.example .env

# 3. seed the vector store (embeds backend/rag/sample_materials/*.md)
python -m backend.rag.seed_content --reset

# 4. run
uvicorn backend.main:app --reload
```

Open <http://127.0.0.1:8000/> for the UI, <http://127.0.0.1:8000/docs> for the API.

## Agents

| Agent | Model | Reads | Writes |
|---|---|---|---|
| Learner Analysis | `mistral-small-latest` | `manager_request` | cohorts, levels, skill gaps, headcount, region |
| Curriculum | `mistral-large-latest` | `learner_analysis` + revision feedback | modules, objectives, sequencing, duration |
| Content | `mistral-small-latest` + ChromaDB | `curriculum` | per-module material reuse **and flagged content gaps** |
| Assessment | `mistral-large-latest` | `curriculum`, `content_plan` | quizzes, coding exercises, rubrics |
| Quality | `mistral-large-latest` | everything above | `verdict`, `issues[]`, `target_agent` |

Model tiering is deliberate: extraction and mapping tasks use the small model, design and
review judgment use the large one. The cost breakdown in the UI makes the trade-off visible.

Every agent goes through [base_agent.call_json()](backend/agents/base_agent.py), which
requests Mistral's JSON mode, validates the response against a Pydantic model, retries on
both API errors and schema violations (feeding the validation error back to the model), and
logs token usage to `state.cost_log`. The orchestrator never parses free text.

## Conflict resolution / revision routing

The Quality Agent returns a `target_agent` — the *earliest* agent in the chain that must
change. The orchestrator re-runs from that agent **onward** (not the whole pipeline), so a
content-only defect doesn't pay for a curriculum redesign. See
[orchestrator.run_pipeline()](backend/orchestrator.py).

A rejection needs at least one `high` or `medium` severity issue; `low` findings are
advisory and cannot block approval. Rejections are capped at `MAX_REVISIONS` (default 3) —
past that, the run is parked as `failed` with an escalation note rather than looping.

### Two separate revision budgets

`MAX_REVISIONS` caps the **automated** loop; `MAX_HUMAN_REJECTIONS` (default 2) caps
**human** rejections independently. They must not share a budget: the automated cap exists
to stop agents revising unattended, and in practice the quality loop often spends its full
budget before approving — if Reject drew from the same pool, the approval gate would be
dead exactly when a human first sees the draft.

So a human rejection **resets** the automated budget, giving the quality loop room to act
on the new requirement. Human feedback is also promoted to a *standing requirement* that
[feedback_block()](backend/agents/base_agent.py) replays on every subsequent lap —
`revision_feedback` is overwritten by each new quality rejection, so without that the
human's instruction would be dropped after one revision.

### Deterministic repairs beat prompt instructions

[curriculum.normalise()](backend/agents/curriculum.py) runs in **code** before the Quality
Agent sees a draft, and fixes three mechanical invariants: `total_duration_hours` is set to
the actual sum of module hours, prerequisites pointing at later or non-existent modules are
stripped, and pathways referencing unknown `module_id`s are cleaned. Every repair is
recorded in `history` as a `normalised` event, so nothing is silently changed.

This exists because of an observed failure: the Quality Agent repeatedly raised a
`high`-severity "hours don't add up" issue against a curriculum whose hours *did* add up —
it miscounted, then routed the fix to the curriculum agent, which regenerated the whole
curriculum and invalidated the assessments. Four laps, no convergence, ~$0.40 spent on a
hallucinated defect. Arithmetic is not a judgment task; code guarantees it and the reviewer
is told not to recount.

## RAG

One Chroma collection, `learning_materials`. `seed_content.py` parses front matter from
each markdown file in `backend/rag/sample_materials/`, embeds it with `mistral-embed`, and
stores metadata `{source, topic, format, level}`.

The Content Agent embeds each module's title + objectives in **one batched embed call**,
queries top-k per module, then asks the model to decide reuse-vs-gap. The seed library
deliberately does **not** cover everything a realistic curriculum needs (no MLOps,
evaluation/observability, or fine-tuning material), so the gap-flagging path actually
fires instead of always finding a match.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Key present, model names, vector-store size |
| POST | `/api/programmes` | Submit request → `202` + `run_id`; orchestration runs in the background |
| GET | `/api/programmes` | Recent runs |
| GET | `/api/programmes/{run_id}` | Poll status, agent states, outputs, running cost |
| GET | `/api/programmes/{run_id}/history` | Full agent-by-agent trace |
| GET | `/api/programmes/{run_id}/cost` | Cost by agent, by model, by revision |
| GET | `/api/programmes/{run_id}/export/{section}.pdf` | Download `curriculum`, `content_plan` or `assessments` as PDF |
| POST | `/api/programmes/{run_id}/approve` | Human sign-off → `approved` |
| POST | `/api/programmes/{run_id}/reject` | Human rejection + feedback → re-enters the revision loop |

## Agent dependencies

Dependencies are **one-directional** — a DAG, not a mesh. Every agent writes exactly one
section and reads only upstream ones; no agent calls another.

```
learner_analysis → curriculum → content → assessment ──┐
                                                       ├→ quality
        ◄──────── target_agent (the only back-edge) ────┘
```

Single-writer sections are what make `run_pipeline(start_from=…)` safe: `assessment` reads
`state.curriculum` without caring when it was written. The cost is **cascade invalidation** —
re-running an upstream agent makes everything downstream stale, which is why routing to
`curriculum` is the most expensive possible route.

Because consistency is maintained only by execution order, nothing structurally prevents a
partially-completed revision from leaving `assessments` referencing a module a later
curriculum re-run deleted. [check_integrity()](backend/orchestrator.py) verifies the
sections describe the same curriculum before the human approval gate opens, and fails the
run rather than presenting an inconsistent draft for sign-off.

## PDF export

[pdf_export.py](backend/pdf_export.py) renders the curriculum, content plan and assessments
to A4 PDFs with ReportLab (pure Python — no system dependencies). The UI exposes them as
three download links on the result card; each is disabled until the owning agent has
produced its section, and the endpoint returns 409 rather than an empty document.

Every page carries the footer *"AI-generated draft - requires human review before use"*,
and the header stamps the run id, status, revision count and generation time — so an
exported document can always be traced back to the run that produced it.

ReportLab's built-in fonts are Latin-1 only while agent output routinely contains arrows,
em-dashes and curly quotes, so `_clean()` maps the characters that actually occur and
replaces anything else unmappable. That avoids both black boxes and a mid-render crash
without shipping a TTF.

## Failure recovery

- **Two retry policies.** Ordinary API errors get `LLM_MAX_ATTEMPTS` (2) with linear
  backoff — fail fast, since an auth or bad-request error won't fix itself. Rate limits
  (HTTP 429) get `LLM_RATE_LIMIT_ATTEMPTS` (5) with exponential backoff capped at 90s
  (~240s of total patience), because a capacity error is transient and worth waiting out.
  A real run died on a 429 after ~2 seconds of retrying before this split existed.
- Schema-invalid output is retried with the validation error appended to the conversation,
  so the model reads its own mistake rather than blindly regenerating.
- An agent that still fails parks the run as `failed`, records the error in `history`, and
  surfaces it in the UI — the API request never crashes.
- The revision loop is hard-capped, and integrity is verified before human sign-off.

## Cost tracking

Every call appends `{agent, model, prompt_tokens, completion_tokens, cost_usd, revision}`
to `state.cost_log`. `/cost` rolls it up three ways, and the UI shows a per-agent table
plus a per-revision table so the price of a Quality Agent rejection is visible.

Prices live in [cost_tracker.PRICING_USD_PER_MTOK](backend/cost_tracker.py) and are
**estimates** — verify against Mistral's pricing page before quoting them.

## Configuration

All via `.env` (see `.env.example`): `MISTRAL_API_KEY`, `CHROMA_PERSIST_DIR`, `RUNS_DIR`,
`LLM_MODEL_LARGE`, `LLM_MODEL_SMALL`, `EMBED_MODEL`, `MAX_REVISIONS`, `RAG_TOP_K`.

## Notes and limits

- Agent output is a **draft**. A named human reviews and owns anything used for a business
  decision — that's what the approval gate is for.
- `data/chroma_db/` and `data/runs/` are gitignored.
- Model IDs use `-latest` aliases so they resolve to whatever Mistral currently ships.
