---
title: Retrieval-Augmented Generation (RAG) Fundamentals
topic: rag
format: workshop
level: intermediate
duration_hours: 8
---

# Retrieval-Augmented Generation (RAG) Fundamentals

A hands-on workshop that builds a working RAG pipeline end to end.

## Contents

1. **Why RAG** — grounding answers in your own documents instead of model memory;
   when fine-tuning is the wrong answer.
2. **Chunking strategies** — fixed-size, sentence-aware, and structure-aware chunking;
   overlap; why chunk boundaries determine retrieval quality.
3. **Embeddings** — vector representations, cosine vs L2 distance, embedding model
   choice, dimensionality, batching embed calls to control cost.
4. **Vector stores** — collections, metadata filtering, persistence, upsert semantics.
   Worked examples in ChromaDB.
5. **Retrieval** — top-k search, metadata pre-filters, hybrid keyword+vector retrieval,
   re-ranking.
6. **Generation** — prompt assembly, citing sources, refusing when retrieval is empty.
7. **Debugging RAG** — the four classic failures: bad chunking, wrong embedding model,
   retrieval returns nothing relevant, model ignores the retrieved context.

## Labs

- Lab 1: chunk and embed a document set into a persistent vector collection.
- Lab 2: query top-k and inspect distances; tune k and chunk size.
- Lab 3: add metadata filters (topic, level) and measure precision change.
- Lab 4: make the model answer "not found in the provided sources" instead of guessing.

## Prerequisites

Generative AI Foundations, or equivalent experience calling an LLM API.
