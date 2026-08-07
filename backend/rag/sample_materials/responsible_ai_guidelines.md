---
title: Responsible AI Guidelines for Engineering Teams
topic: responsible_ai
format: policy guide + workshop
level: beginner
duration_hours: 4
---

# Responsible AI Guidelines for Engineering Teams

Internal policy guide with a half-day workshop. Applies to every team shipping features
built on generative models.

## Contents

1. **Data handling** — never send confidential business data, client information,
   credentials, secrets or personal data to an external model endpoint. Approved
   exceptions must be documented and logged.
2. **Approved tooling** — development AI assistance runs only through the approved IDE
   extension; browser-based tools are not approved for development work.
3. **Human accountability** — model output is a draft. A named human reviews and owns
   any output used in a legal, financial or business decision.
4. **Bias and fairness** — where bias enters (training data, prompt framing, evaluation
   sets), how to test for disparate output quality across groups.
5. **Transparency** — disclose AI involvement in user-facing features; keep an audit
   trail of prompts and outputs for regulated flows.
6. **Privacy and residency** — data residency questions to ask a vendor, retention
   settings, opting out of training.
7. **Security** — prompt injection, data exfiltration through tool calls, over-broad
   tool permissions, secret handling in agent systems.
8. **Incident response** — how to report an AI misuse or data-exposure concern.

## Workshop activities

- Classify ten realistic prompts as approved / needs redaction / prohibited.
- Red-team a sample internal chatbot for prompt injection and data leakage.
- Write a one-page AI usage note for your own team's feature.

## Prerequisites

None. Required for all engineers before production AI work.
