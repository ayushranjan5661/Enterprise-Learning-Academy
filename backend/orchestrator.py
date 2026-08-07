"""Orchestrator — routing logic only, no LLM call of its own.

Responsibilities:
  * run the agent chain in order,
  * run the quality gate and act on its verdict,
  * route a rejection to the owning agent and re-run from there onward,
  * enforce MAX_REVISIONS so the loop can never spin forever,
  * hand an approved draft to the human approval gate,
  * catch agent failures and park the run in `failed` instead of crashing the request.
"""

from __future__ import annotations

import logging

from backend import config, storage
from backend.agents import assessment, content, curriculum, learner_analysis, quality
from backend.agents.base_agent import AgentError
from backend.schemas import PIPELINE_ORDER, ProgrammeState

log = logging.getLogger("orchestrator")

AGENT_FUNCS = {
    "learner_analysis": learner_analysis.run,
    "curriculum": curriculum.run,
    "content": content.run,
    "assessment": assessment.run,
    "quality": quality.run,
}


def _run_agent(state: ProgrammeState, name: str) -> ProgrammeState:
    state.current_agent = name
    state.agent_status[name] = "running"
    storage.record(state, name, "started")
    storage.save(state)

    state = AGENT_FUNCS[name](state)

    state.agent_status[name] = "done"
    state.current_agent = None
    storage.record(state, name, "completed")
    storage.save(state)
    return state


def run_pipeline(state: ProgrammeState, start_from: str | None = None) -> ProgrammeState:
    """Run the build agents. `start_from` restarts mid-chain for a targeted revision."""
    order = PIPELINE_ORDER
    if start_from and start_from in order:
        order = order[order.index(start_from) :]

    for name in order:
        state.agent_status[name] = "pending"
    state.agent_status["quality"] = "pending"
    storage.save(state)

    for name in order:
        state = _run_agent(state, name)
    return state


def check_integrity(state: ProgrammeState) -> list[str]:
    """Verify the sections still describe the SAME curriculum.

    Agent dependencies are one-directional, so consistency is maintained only by execution
    order — nothing structurally prevents `assessments` from referencing a module_id that a
    later curriculum re-run removed. A partially-completed revision can therefore leave the
    state internally inconsistent, and without this check that state is still readable
    through the API as a draft.
    """
    curriculum = state.curriculum or {}
    module_ids = {m.get("module_id") for m in curriculum.get("modules") or []}
    if not module_ids:
        return []

    problems: list[str] = []
    downstream = (
        ("content_plan", (state.content_plan or {}).get("modules") or []),
        ("assessments", (state.assessments or {}).get("per_module") or []),
    )
    for section, rows in downstream:
        if not rows:
            continue
        ids = {r.get("module_id") for r in rows}
        orphans = sorted(i for i in ids - module_ids if i)
        missing = sorted(i for i in module_ids - ids if i)
        if orphans:
            problems.append(f"{section} references module_id(s) not in the curriculum: {orphans}")
        if missing:
            problems.append(f"{section} is missing curriculum module_id(s): {missing}")
    return problems


def orchestrate(state: ProgrammeState, start_from: str | None = None) -> ProgrammeState:
    """Drive the build → review → revise loop until approval, cap, or failure."""
    try:
        while True:
            state.status = "revising" if state.revision_count else "running"
            storage.save(state)

            state = run_pipeline(state, start_from=start_from)
            start_from = None  # only the first lap of a targeted revision is partial

            state = _run_agent(state, "quality")
            review = state.quality_review or {}
            verdict = review.get("verdict", "rejected")
            issues = review.get("issues", [])

            storage.record(
                state,
                "quality",
                "verdict",
                f"{verdict}: {len(issues)} issue(s) raised",
            )

            if verdict == "approved":
                # A human must never be handed an internally inconsistent draft to sign off.
                problems = check_integrity(state)
                if problems:
                    state.status = "failed"
                    state.error = "Inconsistent programme state: " + "; ".join(problems)
                    storage.record(state, "orchestrator", "inconsistent", state.error)
                    log.error("run %s failed integrity check: %s", state.run_id, problems)
                    break

                state.status = "awaiting_approval"
                state.revision_target = None
                storage.record(
                    state, "orchestrator", "awaiting_approval",
                    "Quality Agent approved — integrity verified, routed to human approval gate.",
                )
                break

            if state.revision_count >= config.MAX_REVISIONS:
                state.status = "failed"
                state.error = (
                    f"Quality Agent still rejecting after {config.MAX_REVISIONS} "
                    "revisions — escalated to a human instead of looping."
                )
                storage.record(state, "orchestrator", "escalated", state.error)
                break

            # Route the fix to the owning agent and re-run from there onward.
            state.revision_count += 1
            state.revision_feedback = [
                f"[{i.get('severity', '?')}] {i.get('issue', '')} → FIX: {i.get('required_fix', '')}"
                for i in issues
            ]
            target = review.get("target_agent") or "curriculum"
            state.revision_target = target
            start_from = target
            storage.record(
                state,
                "orchestrator",
                "routed",
                f"Revision {state.revision_count}: rejected → re-running from "
                f"'{target}' agent onward.",
            )
            storage.save(state)

    except AgentError as exc:
        state.status = "failed"
        state.error = str(exc)
        if state.current_agent:
            state.agent_status[state.current_agent] = "failed"
        storage.record(state, state.current_agent or "orchestrator", "failed", str(exc))
        log.exception("run %s failed", state.run_id)
    except Exception as exc:  # never let a background run take the server down
        state.status = "failed"
        state.error = f"unexpected error: {exc}"
        if state.current_agent:
            state.agent_status[state.current_agent] = "failed"
        storage.record(state, state.current_agent or "orchestrator", "failed", str(exc))
        log.exception("run %s crashed", state.run_id)

    return storage.save(state)


def start_run(manager_request: str) -> ProgrammeState:
    """Create and persist a fresh run without executing it."""
    state = ProgrammeState(
        run_id=storage.new_id(),
        manager_request=manager_request.strip(),
        status="running",
        created_at=storage.now_iso(),
    )
    storage.record(state, "orchestrator", "started", "Manager request received.")
    return storage.save(state)


def resume_after_human_rejection(
    state: ProgrammeState, feedback: str, target: str | None
) -> ProgrammeState:
    """Human rejected a draft — feed it back in with a fresh automated revision budget.

    Human rejections are capped separately from `MAX_REVISIONS`. The automated cap exists
    to stop agents revising unattended; a human pressing reject is deliberate, so an
    exhausted agent budget must not disable the approval gate. Each human rejection resets
    the automated budget so the quality loop can actually act on the new requirement.
    """
    if state.human_revision_count >= config.MAX_HUMAN_REJECTIONS:
        state.status = "failed"
        state.error = (
            f"Human rejection cap reached ({config.MAX_HUMAN_REJECTIONS}) — the brief "
            "needs manual redesign rather than another automated pass."
        )
        storage.record(state, "orchestrator", "escalated", state.error)
        return storage.save(state)

    state.human_revision_count += 1
    state.human_decision = "rejected"
    state.human_feedback = feedback  # persists into every later lap via feedback_block()
    # Deliberately NOT copied into revision_feedback: that list is the Quality Agent's
    # channel, and duplicating the human's words into it made every agent read the same
    # instruction twice — once misattributed to the reviewer.
    state.revision_feedback = []
    state.revision_count = 0  # fresh automated budget to satisfy the human's requirement
    state.revision_target = target or "curriculum"
    state.status = "revising"
    state.quality_review = None
    storage.record(
        state,
        "orchestrator",
        "routed",
        f"Human rejection {state.human_revision_count}/{config.MAX_HUMAN_REJECTIONS} → "
        f"re-running from '{state.revision_target}' onward with a reset revision budget.",
    )
    storage.save(state)
    return orchestrate(state, start_from=state.revision_target)
