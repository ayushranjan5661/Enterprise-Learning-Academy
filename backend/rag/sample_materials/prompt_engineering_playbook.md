---
title: Prompt Engineering Playbook
topic: prompting
format: reference guide
level: beginner
duration_hours: 3
---

# Prompt Engineering Playbook

A short reference guide engineers keep open while building.

## Contents

1. **Anatomy of a good prompt** — role, task, constraints, output format, examples.
2. **Structured output** — JSON mode, JSON schema, validating with a typed model,
   repairing invalid output by feeding the validation error back to the model.
3. **Few-shot patterns** — how many examples, choosing hard examples, example ordering.
4. **Decomposition** — splitting one over-loaded prompt into a chain of small,
   individually testable prompts.
5. **Adversarial prompting for review tasks** — instructing a model to look for problems
   rather than agree; asking for severity and an owner, not just commentary.
6. **Prompt regression testing** — a small golden set, asserting on structure not
   wording, catching drift after a model upgrade.
7. **Token discipline** — trimming retrieved context, summarising history, choosing a
   cheaper model where the task is extraction rather than judgment.

## Prerequisites

None.
