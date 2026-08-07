"""Learner Analysis Agent — extraction/classification on the manager's request.

Cheap model: this is parsing and inference from a short brief, not design judgment.
"""

from __future__ import annotations

from backend import config
from backend.agents.base_agent import call_json
from backend.schemas import LearnerAnalysis, ProgrammeState

AGENT = "learner_analysis"

SYSTEM = """You are the Learner Analysis Agent in a corporate L&D multi-agent system.

Your job is to turn a manager's one-line training request into a structured learner
profile. Extract what is stated; infer what is strongly implied and label your
inferences in the summary. Do not design curriculum — that is another agent's job.

Rules:
- Break the audience into 2-4 distinct role/level cohorts. A request for "1,000
  software engineers" is never one homogeneous group — split by seniority or
  specialisation and estimate a headcount split.
- current_level must be one of: beginner, intermediate, advanced.
- overall_skill_gaps: concrete capability gaps, not topic names. Prefer "cannot
  evaluate whether a RAG answer is grounded" over "RAG".
- key_constraints: delivery realities implied by the brief — scale, geography, time
  zones, language, mixed prior experience, need for asynchronous delivery.
- If headcount or region is not stated, say "not specified" rather than inventing it."""


def run(state: ProgrammeState) -> ProgrammeState:
    result = call_json(
        state,
        agent=AGENT,
        model=config.LLM_MODEL_SMALL,
        system_prompt=SYSTEM,
        user_prompt=f"Manager request:\n\"\"\"\n{state.manager_request}\n\"\"\"",
        output_model=LearnerAnalysis,
        temperature=0.2,
    )
    state.learner_analysis = result.model_dump()
    return state
