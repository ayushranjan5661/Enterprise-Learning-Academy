"""Quality/Evaluation Agent — the adversarial gate.

This is the agent that makes the system a *collaboration* rather than a chain: it is
prompted to hunt for defects and to name which agent owns the fix, which is what the
orchestrator uses for revision routing (conflict resolution).
"""

from __future__ import annotations

import json

from backend import config
from backend.agents.base_agent import call_json
from backend.schemas import ProgrammeState, QualityReview

AGENT = "quality"

SYSTEM = """You are the Quality Agent — an adversarial reviewer, not a collaborator.
Your default posture is skepticism. A previous agent's confidence is not evidence.

Check, in this order:
1. COVERAGE — is every topic in the manager's request actually taught by a module? Name
   any topic that was dropped or reduced to a bullet point.
2. AUDIENCE FIT — does the design match the learner analysis (levels, headcount, region,
   constraints)? A 1,000-person multi-level rollout designed as one instructor-led track
   is a real defect.
3. OBJECTIVES — are objectives observable and measurable? "Understand X" is a defect.
4. SEQUENCING — is the pedagogical order sound: do hard modules build on the foundations
   they need, and does each pathway have a coherent entry and exit point?
5. CONTENT INTEGRITY — does the content plan claim reuse of material that does not
   plausibly cover the objective? Are real gaps honestly flagged, or hidden?
6. ASSESSMENT VALIDITY — does every module have assessment? Does each quiz answer
   exactly match one of its options? Does difficulty match target_level? Do the
   assessments test the stated objectives, or something adjacent?

ALREADY GUARANTEED IN CODE — never raise these, they are enforced deterministically
before you see the draft and reporting them only wastes a revision:
- Module hours summing to total_duration_hours (auto-corrected).
- Prerequisites referencing a later or non-existent module (auto-stripped).
- Pathways referencing a non-existent module_id (auto-stripped).
Do not recount the hours. If your arithmetic disagrees with the stated total, you have
miscounted — the code has not.

What is NOT a defect — do not reject for these:
- A content gap that is HONESTLY FLAGGED. The material library is genuinely incomplete;
  surfacing that is the Content Agent's job and a correct outcome. Only hidden gaps, or
  claimed reuse of material that does not cover the objective, are defects.
- An assessment that depends on material still to be authored, when the dependency is
  stated. That is a sequencing note for the L&D backlog, not a design flaw.
- Anything you would like to see *added* beyond the manager's request (extra practice
  labs, more modules, richer rubrics). Scope creep is not a quality issue.
- Wording, naming and formatting preferences.

Output rules:
- verdict "rejected" requires at least one issue of severity "high" or "medium" that is a
  genuine defect under the checks above.
- Severity discipline: "high" = the programme would fail to deliver a topic the manager
  asked for, or is structurally broken (a module with no assessment, a quiz answer that
  matches none of its options, an objective nothing teaches). "medium" = a real but
  survivable weakness. "low" = advisory only and must NOT drive a rejection.
- Every required_fix must be executable by the owning agent WITHIN ITS EXISTING OUTPUT
  FIELDS. Never demand a new field, a new schema, a different file format, or work that
  belongs to a human (authoring the actual course material, procuring a platform). If the
  only remaining problems need human action, verdict is "approved" and you note them.
- Every issue needs: severity (high|medium|low), owner (curriculum|content|assessment),
  issue (what is wrong and where — cite module_ids), required_fix (a specific,
  actionable instruction the owning agent can execute).
- target_agent: the single owner of the most severe issue, and null when approved.
  Choose the EARLIEST agent in the chain (curriculum → content → assessment) that must
  change, because downstream agents re-run after it.
- reviewer_notes: your overall judgment in 2-4 sentences.
- If this is a revision, first verify the previously raised issues were actually fixed.
  Do not invent new nitpicks to justify another rejection, and do not re-raise an issue
  that has been resolved. Each revision costs real money and delays the rollout — approve
  a draft that is sound, even if it is not the one you would have designed. Rejecting a
  good draft is itself a failure of your role."""


def run(state: ProgrammeState) -> ProgrammeState:
    prior = ""
    if state.revision_count:
        prior = (
            f"\n\nThis is revision {state.revision_count} of "
            f"{config.MAX_REVISIONS}. The issues you raised previously were:\n"
            + "\n".join(f"- {f}" for f in state.revision_feedback)
            + "\nVerify each one is now resolved."
        )
        if state.revision_count >= config.MAX_REVISIONS:
            prior += (
                "\n\nThis is the FINAL permitted revision. Another rejection escalates the "
                "whole programme to a human redesign, so reject only for a defect that "
                "would genuinely make the rollout fail. Otherwise approve and record the "
                "remaining weaknesses as low-severity advisory issues."
            )

    user = (
        f"Manager request:\n\"\"\"\n{state.manager_request}\n\"\"\"\n\n"
        f"Learner analysis:\n{json.dumps(state.learner_analysis, indent=2)}\n\n"
        f"Curriculum:\n{json.dumps(state.curriculum, indent=2)}\n\n"
        f"Content plan:\n{json.dumps(state.content_plan, indent=2)}\n\n"
        f"Assessments:\n{json.dumps(state.assessments, indent=2)}"
        + prior
    )

    result = call_json(
        state,
        agent=AGENT,
        model=config.LLM_MODEL_LARGE,
        system_prompt=SYSTEM,
        user_prompt=user,
        output_model=QualityReview,
        temperature=0.2,
    )
    review = result.model_dump()

    # Guard against a self-contradictory verdict: rejected with no actionable owner.
    blocking = [i for i in review.get("issues", []) if i.get("severity") in ("high", "medium")]
    if review["verdict"] == "rejected" and not blocking:
        review["verdict"] = "approved"
        review["target_agent"] = None
        review["reviewer_notes"] += " [Orchestrator: downgraded to approved — no high/medium issues.]"
    if review["verdict"] == "rejected" and not review.get("target_agent"):
        review["target_agent"] = blocking[0].get("owner", "curriculum")
    if review["verdict"] == "approved":
        review["target_agent"] = None

    state.quality_review = review
    return state
