"""Pydantic models. `ProgrammeState` is the single object that flows through every agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal[
    "learner_analysis", "curriculum", "content", "assessment", "quality"
]
RunStatus = Literal[
    "running", "revising", "awaiting_approval", "approved", "rejected", "failed"
]

# Order matters: revision routing re-runs from the target agent onward.
PIPELINE_ORDER: list[str] = ["learner_analysis", "curriculum", "content", "assessment"]


# --------------------------------------------------------------------------
# Agent output contracts (also used to build the JSON schema shown to the LLM)
# --------------------------------------------------------------------------
class LearnerProfile(BaseModel):
    role: str
    current_level: str = Field(description="beginner | intermediate | advanced")
    headcount_estimate: int | str
    skill_gaps: list[str] = []


class LearnerAnalysis(BaseModel):
    total_learners: int | str
    region: str
    roles: list[LearnerProfile]
    overall_skill_gaps: list[str]
    key_constraints: list[str] = []
    summary: str


class Module(BaseModel):
    module_id: str
    title: str
    topic: str
    target_level: str
    pathway: str = Field(
        default="all",
        description="Which cohort track this module belongs to: beginner | intermediate | advanced | all",
    )
    duration_hours: float
    learning_objectives: list[str]
    prerequisites: list[str] = []
    delivery_mode: str = "blended"


class Curriculum(BaseModel):
    programme_title: str
    total_duration_hours: float
    sequencing_rationale: str
    pathways: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Track name -> ordered module_ids a learner on that track takes",
    )
    modules: list[Module]


class ModuleContent(BaseModel):
    module_id: str
    module_title: str
    recommended_materials: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each item: {source, topic, level, why_relevant}",
    )
    gap: bool = False
    gap_note: str | None = None


class ContentPlan(BaseModel):
    modules: list[ModuleContent]
    content_gaps: list[str] = []
    reuse_summary: str


class Assessment(BaseModel):
    module_id: str
    quiz: list[dict[str, Any]] = Field(
        default_factory=list, description="Each item: {question, options, answer}"
    )
    coding_exercise: dict[str, Any] | None = None
    practical_rubric: list[dict[str, Any]] = Field(
        default_factory=list, description="Each item: {criterion, levels}"
    )


class Assessments(BaseModel):
    per_module: list[Assessment]
    certification_note: str


class QualityIssue(BaseModel):
    severity: str = Field(description="high | medium | low")
    owner: str = Field(description="curriculum | content | assessment")
    issue: str
    required_fix: str


class QualityReview(BaseModel):
    verdict: Literal["approved", "rejected"]
    issues: list[QualityIssue] = []
    target_agent: Literal["curriculum", "content", "assessment"] | None = None
    reviewer_notes: str


# --------------------------------------------------------------------------
# Run state
# --------------------------------------------------------------------------
class CostEntry(BaseModel):
    agent: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    revision: int = 0
    calls: int = 1


class HistoryEntry(BaseModel):
    agent: str
    event: str  # started | completed | failed | verdict | routed | escalated
    revision: int = 0
    detail: str = ""
    timestamp: str


class ProgrammeState(BaseModel):
    run_id: str
    manager_request: str
    learner_analysis: dict | None = None
    curriculum: dict | None = None
    content_plan: dict | None = None
    assessments: dict | None = None
    quality_review: dict | None = None
    status: RunStatus = "running"
    current_agent: str | None = None
    agent_status: dict[str, str] = Field(
        default_factory=lambda: {
            name: "pending"
            for name in ["learner_analysis", "curriculum", "content", "assessment", "quality"]
        }
    )
    revision_count: int = 0          # laps of the automated quality-gate loop
    human_revision_count: int = 0    # laps triggered by a human pressing "reject"
    revision_feedback: list[str] = []
    revision_target: str | None = None
    cost_log: list[dict] = []
    history: list[dict] = []
    error: str | None = None
    human_decision: str | None = None
    human_feedback: str | None = None
    created_at: str = ""
    updated_at: str = ""


# --------------------------------------------------------------------------
# API request/response bodies
# --------------------------------------------------------------------------
class CreateProgrammeRequest(BaseModel):
    manager_request: str = Field(min_length=10)


class RejectRequest(BaseModel):
    feedback: str = Field(default="", description="Why the human rejected the draft")
    target_agent: Literal["curriculum", "content", "assessment"] | None = None
