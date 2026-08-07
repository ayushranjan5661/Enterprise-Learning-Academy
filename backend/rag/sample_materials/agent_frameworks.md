---
title: Building AI Agents — Patterns and Frameworks
topic: agents
format: instructor-led course
level: advanced
duration_hours: 12
---

# Building AI Agents — Patterns and Frameworks

A twelve-hour instructor-led course on designing systems where an LLM decides what to
do next, not just what to say.

## Contents

1. **Agent vs pipeline** — when tool-calling loops beat a fixed chain, and when they
   are simply a more expensive way to get the same answer.
2. **Tool use / function calling** — describing tools to a model, validating arguments,
   handling tool errors, keeping tool output small.
3. **The core loop** — plan → act → observe → repeat; termination conditions; step caps
   as a hard safety net against runaway loops.
4. **Multi-agent orchestration** — specialised agents, shared state objects, handoffs,
   a supervisor/orchestrator that owns routing rather than reasoning.
5. **Critic and quality-gate patterns** — an adversarial reviewer agent, verdict plus
   routed feedback, revision caps, escalation to a human on repeated failure.
6. **State and memory** — short-term scratchpads, run history for audit, persisting
   intermediate state so a failed run can be inspected.
7. **Human-in-the-loop** — approval gates, editable drafts, rejection feedback flowing
   back into the loop.
8. **Cost control in agent systems** — model tiering per agent, token budgets, logging
   every call, per-revision cost attribution.

## Labs

- Lab 1: single agent with two tools and a step cap.
- Lab 2: two agents passing a typed state object.
- Lab 3: add a critic agent that can reject and route work back.
- Lab 4: add a human approval gate and a cost dashboard.

## Prerequisites

RAG Fundamentals plus solid backend engineering experience.
