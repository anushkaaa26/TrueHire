import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import asyncpg
from app.ghost.scorer import score_features
from app.ingestion.embedder import embed_texts, format_pgvector
from app.retrieval.pipeline import hybrid_search

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

BM25_ONLY_SQL = """
SELECT
    j.id AS job_id,
    ts_rank_cd(j.tsv, websearch_to_tsquery('english', $1)) AS score
FROM jobs j
WHERE j.is_active = TRUE
  AND j.tsv @@ websearch_to_tsquery('english', $1)
ORDER BY score DESC
LIMIT $2
"""

DENSE_ONLY_SQL = """
SELECT
    j.id AS job_id,
    1.0 - (j.embedding <=> $1::vector) AS score
FROM jobs j
WHERE j.is_active = TRUE
  AND j.embedding IS NOT NULL
ORDER BY j.embedding <=> $1::vector ASC
LIMIT $2
"""


def dcg_at_k(rels: list[int], k: int) -> float:
    total = 0.0
    for idx, g in enumerate(rels[:k]):
        gain = (2**g) - 1
        total += gain / math.log2(idx + 2)
    return total


def ndcg_at_k(ranked_ids: list[int], grades_by_job: dict[int, int], k: int = 10) -> float:
    actual = [grades_by_job.get(jid, 0) for jid in ranked_ids[:k]]
    ideal = sorted(grades_by_job.values(), reverse=True)[:k]
    idcg = dcg_at_k(ideal, k)
    if idcg == 0.0:
        return 0.0
    return dcg_at_k(actual, k) / idcg


def recall_at_k(ranked_ids: list[int], grades_by_job: dict[int, int], k: int = 20) -> float:
    relevant = {jid for jid, g in grades_by_job.items() if g >= 1}
    if not relevant:
        return 0.0
    hit = sum(1 for jid in ranked_ids[:k] if jid in relevant)
    return hit / len(relevant)


def mrr_at_k(ranked_ids: list[int], grades_by_job: dict[int, int], k: int = 10) -> float:
    for idx, jid in enumerate(ranked_ids[:k]):
        if grades_by_job.get(jid, 0) >= 1:
            return 1.0 / (idx + 1)
    return 0.0


def evaluate_ghost_set(samples: list[tuple[dict[str, float], int]], threshold: float = 0.5) -> dict:
    tp = fp = fn = tn = 0
    for feats, label in samples:
        pred = 1 if score_features(feats).probability >= threshold else 0
        if pred == 1 and label == 1:
            tp += 1
        elif pred == 1 and label == 0:
            fp += 1
        elif pred == 0 and label == 1:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


async def _rank_for_query(
    conn: asyncpg.Connection,
    mode: str,
    query_text: str,
    q_vec_str: str,
    user_skills: list[str],
) -> list[int]:
    if mode == "bm25":
        rows = await conn.fetch(BM25_ONLY_SQL, query_text, 20)
        return [int(r["job_id"]) for r in rows]
    if mode == "dense":
        rows = await conn.fetch(DENSE_ONLY_SQL, q_vec_str, 20)
        return [int(r["job_id"]) for r in rows]
    if mode == "hybrid_rrf":
        hits = await hybrid_search(
            conn=conn,
            query=query_text,
            user_skills=[],
            top_k=20,
            use_rerank=False,
        )
        return [int(h["job_id"]) for h in hits]
    if mode == "hybrid_rrf_rerank_personalize":
        hits = await hybrid_search(
            conn=conn,
            query=query_text,
            user_skills=user_skills,
            top_k=20,
            use_rerank=True,
        )
        return [int(h["job_id"]) for h in hits]
    raise ValueError(f"Unknown ablation mode: {mode}")


async def evaluate_retrieval_configs(conn: asyncpg.Connection) -> dict:
    queries = await conn.fetch("SELECT id, text FROM eval_queries ORDER BY id")
    labels_rows = await conn.fetch("SELECT query_id, job_id, grade FROM eval_labels")

    labels_by_query: dict[int, dict[int, int]] = {}
    for r in labels_rows:
        labels_by_query.setdefault(int(r["query_id"]), {})[int(r["job_id"])] = int(r["grade"])

    query_texts = [q["text"] for q in queries]
    query_vecs = embed_texts(query_texts) if query_texts else []
    vec_by_qid = {int(q["id"]): format_pgvector(v) for q, v in zip(queries, query_vecs)}

    modes = [
        ("bm25", "BM25 only"),
        ("dense", "Dense only"),
        ("hybrid_rrf", "Hybrid RRF"),
        ("hybrid_rrf_rerank_personalize", "+ rerank + personalization"),
    ]

    sample_skills = ["python", "fastapi", "postgresql", "sql", "docker", "react", "pytorch"]
    report: dict[str, dict] = {}

    for mode_key, display_name in modes:
        ndcgs, recalls, mrrs = [], [], []
        for q in queries:
            qid = int(q["id"])
            gmap = labels_by_query.get(qid, {})
            if not gmap:
                continue
            ranked_ids = await _rank_for_query(conn, mode_key, q["text"], vec_by_qid[qid], sample_skills)
            ndcgs.append(ndcg_at_k(ranked_ids, gmap, 10))
            recalls.append(recall_at_k(ranked_ids, gmap, 20))
            mrrs.append(mrr_at_k(ranked_ids, gmap, 10))

        report[mode_key] = {
            "label": display_name,
            "queries_evaluated": len(ndcgs),
            "ndcg_at_10": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0,
            "recall_at_20": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
            "mrr_at_10": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0,
        }

    print("\n=== Retrieval Ablation Summary ===")
    print(f"{'Config':<30} {'nDCG@10':>9} {'Recall@20':>10} {'MRR@10':>9}")
    print("-" * 62)
    for mode_key, _ in modes:
        m = report[mode_key]
        print(f"{m['label']:<30} {m['ndcg_at_10']:>9.4f} {m['recall_at_20']:>10.4f} {m['mrr_at_10']:>9.4f}")
    print()

    return report


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    try:
        retrieval_metrics = await evaluate_retrieval_configs(conn)
        ghost_demo = evaluate_ghost_set(
            [
                ({"reposts_90d": 3.0, "days_vs_median_ratio": 2.5, "stale_no_edits": 1.0, "specificity_count": 1.0, "high_boilerplate_peers": 2.0}, 1),
                ({"reposts_90d": 0.0, "days_vs_median_ratio": 0.6, "stale_no_edits": 0.0, "specificity_count": 12.0, "high_boilerplate_peers": 0.0}, 0),
            ]
        )
        summary = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "retrieval": retrieval_metrics,
            "ghost_scorer_smoke": ghost_demo,
        }
        await conn.execute(
            "INSERT INTO eval_runs (config, metrics) VALUES ($1::jsonb, $2::jsonb)",
            json.dumps({"suite": "retrieval_4way_ablation_v1"}),
            json.dumps(summary),
        )
        out_path = Path("evals/results/latest_eval.json")
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
