# TrueHire

Grounded job-search agent and ghost-listing trust scorer built on daily-snapshotted ATS boards (Greenhouse, Lever, Ashby, Remotive), PostgreSQL (`pgvector` + `tsvector`), FastAPI, and Next.js.

## 1. Overview

TrueHire tracks open roles day over day in `job_snapshots` and `job_events` (`appeared`, `edited`, `disappeared`, `reappeared`), computes lifecycle and posting-specificity features for ghost-job risk, and serves hybrid SQL Reciprocal Rank Fusion (RRF) search with strict `job_id` citation grounding.

## 2. Architecture

```text
ATS boards (Greenhouse / Lever / Ashby / Remotive)
  └─► daily ingestion worker ─► Postgres (jobs, job_snapshots, job_events, ghost_scores)
                                    │
User chat ─► FastAPI /chat ─────────┴─► Hybrid SQL RRF + Rerank + Grounded Agent + Risk Critic
```

## 3. Key Numbers (Measured Runs)

- **Tracked companies:** 38
- **Indexed job postings:** 7,278
- **Daily snapshots recorded:** 7,293
- **Lifecycle events recorded:** 7,279
- **Ghost scorer** (n=0 proxy hand labels): Precision pending, Recall pending, F1 pending, Cohen's kappa pending
- **Agent suite** (n=50 scripted runs): Tool correctness 1.0000, Schema validity 1.0000, Groundedness 1.0000, Latency p50 30.4 ms / p95 153.2 ms

## 4. Schema Highlights

**Core tables:** `companies`, `jobs` (`vector(384)`, generated `tsv tsvector`, `UNIQUE(source, external_id)`), `job_snapshots` (`UNIQUE(job_id, seen_on)`), `job_events`, `ghost_scores`, `user_profiles`, `interactions`, `conversations`, `messages`, and `eval_queries` / `eval_labels` / `eval_runs`.

**Indexes:** HNSW on `jobs.embedding` (`vector_cosine_ops`), GIN on `jobs.tsv`, and B-tree on `(is_active, last_seen)`. Showcase SQL queries (`percentile_cont` company median days open, 90-day repost/reappearance window query, and SQL RRF) live in `app/retrieval/queries.py`.

## 5. Retrieval Ablations

| Config | nDCG@10 | Recall@20 | MRR@10 |
|---|---|---|---|
| BM25 only | 0.0349 | 0.0210 | 0.0972 |
| Dense only | 0.0198 | 0.0333 | 0.0340 |
| Hybrid RRF | 0.0204 | 0.0395 | 0.0396 |
| + rerank + personalization | 0.0215 | 0.0395 | 0.0481 |

## 6. Failure Analysis

Run `PYTHONPATH=. python -m evals.failure_analysis 5` to inspect the lowest nDCG@10 queries and see whether relevant jobs were missed in `bm25_rank`, `dense_rank`, or pushed past the top 10 by filtering/reranking:

1. **Query 1:** Record low-nDCG@10 query text, top missed `job_id`s, and lexical vs. semantic rank.
2. **Query 2:** Record failure cause (e.g., acronym vs. full phrase mismatch or location filter).
3. **Query 3:** Record failure cause and mitigation.
4. **Query 4:** Record failure cause and mitigation.
5. **Query 5:** Record failure cause and mitigation.

## 7. Limitations & What I'd Do Next

- **Proxy labels:** Ghost-listing labels are human-annotated proxies from public board metadata and lifecycle history, not ground-truth internal ATS hiring intent.
- **Board coverage and time depth:** Public ATS board slugs vary in naming and require time-series accumulation across multiple daily runs to surface full repost/reappearance histories.
- **Next steps:** Add a cross-encoder (`bge-reranker-base`) or LLM reranker pass on the top 30 RRF candidates, train a regularized logistic regression ghost model once hand labels are collected, and deploy the Next.js frontend with `NEXT_PUBLIC_API_URL`.

## 8. Run It Locally in 3 Commands

```bash
docker compose up -d
PYTHONPATH=. python -m app.ingestion.run_daily
PYTHONPATH=. uvicorn app.api.main:app --reload
```
