"""Assessment Agent — quizzes, coding exercises and rubrics per module."""

from __future__ import annotations

import json

from backend import config
from backend.agents.base_agent import call_json, feedback_block
from backend.schemas import Assessments, ProgrammeState

AGENT = "assessment"

SYSTEM = """You are the Assessment Agent. You design assessment that proves the learning
objectives were actually met.

Rules:
- One entry per curriculum module, keyed by the SAME module_id. Skip none.
- quiz: 2-4 items, each {question, options (3-4 strings), answer (must exactly match one
  option), rationale}. Test application and judgment, not vocabulary recall.
- coding_exercise: {title, brief, starter_hint, acceptance_criteria (list),
  estimated_minutes}. Omit (null) only for modules with no code component, such as pure
  policy modules — and say so in the brief of the rubric instead.
- practical_rubric: 2-4 items, each {criterion, levels: {novice, competent, proficient}}.
  Levels must be observable and distinguishable, not "does it well / does it badly".
- Assessment difficulty must match the module's target_level.
- Where the content plan flags a GAP, the assessment must still exist — note in the
  coding_exercise brief that it depends on material yet to be authored.
- certification_note: what a learner must pass to be certified, and the pass threshold."""


def run(state: ProgrammeState) -> ProgrammeState:
    user = (
        "Curriculum:\n"
        f"{json.dumps(state.curriculum, indent=2)}\n\n"
        "Content plan (note the gaps):\n"
        f"{json.dumps(state.content_plan, indent=2)}"
        + feedback_block(state, "assessment")
    )
    result = call_json(
        state,
        agent=AGENT,
        model=config.LLM_MODEL_LARGE,
        system_prompt=SYSTEM,
        user_prompt=user,
        output_model=Assessments,
        temperature=0.4,
    )
    state.assessments = result.model_dump()
    return state
