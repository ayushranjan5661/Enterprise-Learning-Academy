"""Curriculum Agent — instructional design. Large model: this needs real judgment."""

from __future__ import annotations

import json

from backend import config, storage
from backend.agents.base_agent import call_json, feedback_block
from backend.schemas import Curriculum, ProgrammeState

AGENT = "curriculum"

SYSTEM = """You are the Curriculum Agent, an experienced instructional designer for
enterprise technical training.

Given a learner analysis, design a modular programme.

Rules:
- 5-9 modules, never more. Each module has a stable module_id like "M1", "M2", ... in
  delivery order. Keep ids simple — do not invent suffixed variants like "M3-B".
- Every module needs 2-4 learning objectives written as observable behaviours using
  Bloom-style action verbs (build, evaluate, debug, justify) — never "understand" or
  "learn about".
- Handle mixed skill levels with PATHWAYS, not duplicate modules. Set each module's
  `pathway` to one of: beginner, intermediate, advanced, all. Then fill `pathways` with
  one entry per cohort in the learner analysis, mapping the track name to the ordered
  module_ids a learner on that track takes. Shared modules appear in several pathways.
- sequencing_rationale must explain the dependency order, the entry/exit point of each
  pathway, and how the sequence handles the mixed skill levels in the learner analysis.
- prerequisites reference earlier module_ids only. No forward or circular references.
- duration_hours must be realistic for the stated audience size, and the module hours
  must sum exactly to total_duration_hours.
- target_level must be one of: beginner, intermediate, advanced.
- Cover every topic the manager asked for. Do not silently drop one.
- delivery_mode should reflect the constraints in the learner analysis (self-paced,
  instructor-led, blended, cohort-based)."""


def normalise(curriculum: dict) -> list[str]:
    """Deterministic repairs applied before the Quality Agent ever sees the draft.

    Never ask an LLM to do what code can guarantee. Hour sums and prerequisite ordering
    are mechanical constraints; leaving them to the model produced a `high`-severity
    arithmetic rejection on every lap, and because the fix routed to the curriculum agent
    the whole curriculum regenerated each time with *different* wrong hours — the loop
    never converged. Fixing it here removes that failure class entirely.
    """
    notes: list[str] = []
    modules = curriculum.get("modules") or []

    # 1. total_duration_hours must equal the sum of module hours.
    actual = round(sum(float(m.get("duration_hours") or 0) for m in modules), 2)
    stated = round(float(curriculum.get("total_duration_hours") or 0), 2)
    if abs(actual - stated) > 0.01:
        curriculum["total_duration_hours"] = actual
        notes.append(f"total_duration_hours corrected {stated}h -> {actual}h (sum of modules)")

    # 2. prerequisites may only reference modules that appear earlier in delivery order.
    position = {m.get("module_id"): i for i, m in enumerate(modules)}
    for i, module in enumerate(modules):
        declared = list(module.get("prerequisites") or [])
        valid = [p for p in declared if p in position and position[p] < i]
        if valid != declared:
            dropped = sorted(set(declared) - set(valid))
            module["prerequisites"] = valid
            notes.append(
                f"{module.get('module_id')}: dropped forward/unknown prerequisite(s) {dropped}"
            )

    # 3. pathways may only reference module_ids that exist.
    pathways = curriculum.get("pathways") or {}
    for track, ids in list(pathways.items()):
        valid = [m for m in (ids or []) if m in position]
        if valid != list(ids or []):
            unknown = sorted(set(ids or []) - set(valid))
            pathways[track] = valid
            notes.append(f"pathway '{track}': dropped unknown module_id(s) {unknown}")

    return notes


def run(state: ProgrammeState) -> ProgrammeState:
    user = (
        "Learner analysis:\n"
        f"{json.dumps(state.learner_analysis, indent=2)}\n\n"
        f"Original manager request: {state.manager_request}"
        + feedback_block(state, "curriculum")
    )
    result = call_json(
        state,
        agent=AGENT,
        model=config.LLM_MODEL_LARGE,
        system_prompt=SYSTEM,
        user_prompt=user,
        output_model=Curriculum,
        temperature=0.4,
    )
    curriculum = result.model_dump()
    notes = normalise(curriculum)
    if notes:
        storage.record(state, AGENT, "normalised", "; ".join(notes))
    state.curriculum = curriculum
    return state
