"""Render README.md from live Postgres stats and eval result JSON files.

Usage (from the repo root):
    PYTHONPATH=. python -m scripts.render_readme

Note: this regenerates README.md in full, so keep any manual edits in this
template rather than in the README itself.
"""

import asyncio
import json
import os
from pathlib import Path

import asyncpg

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"
EVAL_PATH = Path("evals/results/latest_eval.json")
GHOST_EVAL_PATH = Path("evals/results/latest_ghost_eval.json")
AGENT_EVAL_PATH = Path("evals/results/latest_agent_eval.json")
README_PATH = Path("README.md")

RETRIEVAL_CONFIGS = [
    ("bm25", "BM25 only"),
    ("dense", "Dense only"),
    ("hybrid_rrf", "Hybrid RRF"),
    ("hybrid_rrf_rerank_personalize", "+ rerank + personalization"),
]


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning {} if it is missing or malformed."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


async def _fetch_db_stats() -> dict[str, int | None]:
    """Return table row counts, or None for each count if the DB is unreachable."""
    keys = {
        "companies": "companies",
        "jobs": "jobs",
        "snapshots": "job_snapshots",
        "events": "job_events",
    }
    stats: dict[str, int | None] = {k: None for k in keys}

    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    try:
        conn = await asyncpg.connect(db_url)
    except Exception as exc:  # connection refused, bad credentials, etc.
        print(f"Warning: could not connect to database ({exc}); stats will show n/a")
        return stats

    try:
        for key, table in keys.items():
            try:
                stats[key] = int(await conn.fetchval(f"SELECT COUNT(*) FROM {table}") or 0)
            except Exception as exc:  # table missing, permissions, etc.
                print(f"Warning: could not count {table} ({exc})")
    finally:
        await conn.close()
    return stats


def _is_num(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _fmt_metric(val: object) -> str:
    return f"{val:.4f}" if _is_num(val) else "pending"


def _fmt_ms(val: object) -> str:
    return f"{val:.1f} ms" if _is_num(val) else "pending"


def _fmt_count(val: int | None) -> str:
    return "n/a" if val is None else f"{val:,}"


def _build_ablation_table(retrieval: dict) -> str:
    lines = [
        "| Config | nDCG@10 | Recall@20 | MRR@10 |",
        "|---|---|---|---|",
    ]
    for key, label in RETRIEVAL_CONFIGS:
        m = retrieval.get(key, {}) or {}
        lines.append(
            f"| {label} | {_fmt_metric(m.get('ndcg_at_10'))} "
            f"| {_fmt_metric(m.get('recall_at_20'))} "
            f"| {_fmt_metric(m.get('mrr_at_10'))} |"
        )
    return "\n".join(lines)


async def render() -> None:
    stats = await _fetch_db_stats()
    eval_data = _load_json(EVAL_PATH)
    ghost_data = _load_json(GHOST_EVAL_PATH)
    agent_data = _load_json(AGENT_EVAL_PATH)

    retrieval = eval_data.get("retrieval", {}) or {}
    ablation_table = _build_ablation_table(retrieval)

    g_prec = _fmt_metric(ghost_data.get("precision"))
    g_rec = _fmt_metric(ghost_data.get("recall"))
    g_f1 = _fmt_metric(ghost_data.get("f1"))
    g_n = ghost_data.get("labeled_samples", 0)
    kappa = _fmt_metric((ghost_data.get("inter_labeler_agreement") or {}).get("cohens_kappa"))

    a_n = agent_data.get("conversations_evaluated", 0)
    a_tool = _fmt_metric(agent_data.get("tool_call_correctness_rate"))
    a_schema = _fmt_metric(agent_data.get("schema_validity_rate"))
    a_ground = _fmt_metric(agent_data.get("groundedness_rate"))
    lat = agent_data.get("latency_ms") or {}
    a_p50 = _fmt_ms(lat.get("p50"))
    a_p95 = _fmt_ms(lat.get("p95"))

    content = f"""# TrueHire

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

- **Tracked companies:** {_fmt_count(stats["companies"])}
- **Indexed job postings:** {_fmt_count(stats["jobs"])}
- **Daily snapshots recorded:** {_fmt_count(stats["snapshots"])}
- **Lifecycle events recorded:** {_fmt_count(stats["events"])}
- **Ghost scorer** (n={g_n} proxy hand labels): Precision {g_prec}, Recall {g_rec}, F1 {g_f1}, Cohen's kappa {kappa}
- **Agent suite** (n={a_n} scripted runs): Tool correctness {a_tool}, Schema validity {a_schema}, Groundedness {a_ground}, Latency p50 {a_p50} / p95 {a_p95}

## 4. Schema Highlights

**Core tables:** `companies`, `jobs` (`vector(384)`, generated `tsv tsvector`, `UNIQUE(source, external_id)`), `job_snapshots` (`UNIQUE(job_id, seen_on)`), `job_events`, `ghost_scores`, `user_profiles`, `interactions`, `conversations`, `messages`, and `eval_queries` / `eval_labels` / `eval_runs`.

**Indexes:** HNSW on `jobs.embedding` (`vector_cosine_ops`), GIN on `jobs.tsv`, and B-tree on `(is_active, last_seen)`. Showcase SQL queries (`percentile_cont` company median days open, 90-day repost/reappearance window query, and SQL RRF) live in `app/retrieval/queries.py`.

## 5. Retrieval Ablations

{ablation_table}

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
"""

    README_PATH.write_text(content, encoding="utf-8")
    print(
        f"Updated {README_PATH} with stats={stats}, "
        f"retrieval_modes={len(retrieval)}, agent_runs={a_n}"
    )


if __name__ == "__main__":
    asyncio.run(render())
