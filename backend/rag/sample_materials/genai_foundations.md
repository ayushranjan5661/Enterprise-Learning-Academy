---
title: Generative AI Foundations for Software Engineers
topic: genai
format: self-paced course
level: beginner
duration_hours: 6
---

# Generative AI Foundations for Software Engineers

A six-hour self-paced course introducing large language models to engineers who have
never worked with them.

## Contents

1. **What an LLM actually is** — next-token prediction, training vs inference, why a
   model has no memory between calls.
2. **Tokens, context windows and limits** — how text becomes tokens, why long inputs
   cost more, what happens when the context window overflows.
3. **Calling a model from code** — chat completion APIs, system vs user roles,
   temperature, top-p, streaming responses.
4. **Prompt engineering basics** — instruction clarity, few-shot examples, output
   formats, JSON mode / structured output.
5. **Failure modes** — hallucination, refusal, truncation, prompt injection, silent
   format drift; why every LLM output needs validation.
6. **Cost and latency thinking** — pricing per million tokens, choosing a small model
   for extraction and a large model for reasoning, caching repeated prompts.

## Labs

- Lab 1: call a chat completion endpoint and print token usage.
- Lab 2: force a JSON schema out of a model and validate it with Pydantic.
- Lab 3: measure cost difference between a small and a large model on the same task.

## Prerequisites

Working Python or JavaScript, comfort with HTTP APIs. No ML background required.
