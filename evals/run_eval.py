import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import asyncpg
from app.ghost.scorer import score_features
from app.retrieval.pipeline import hybrid_search

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"


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


async def evaluate_retrieval_configs(conn: asyncpg.Connection) -> dict:
    queries = await conn.fetch("SELECT id, text FROM eval_queries ORDER BY id")
    labels_rows = await conn.fetch("SELECT query_id, job_id, grade FROM eval_labels")

    labels_by_query: dict[int, dict[int, int]] = {}
    for r in labels_rows:
        labels_by_query.setdefault(int(r["query_id"]), {})[int(r["job_id"])] = int(r["grade"])

    configs = {
        "hybrid_rrf_rerank": {"use_rerank": True, "skills": ["python", "fastapi", "sql"]},
        "hybrid_rrf_no_rerank": {"use_rerank": False, "skills": []},
    }

    report: dict[str, dict] = {}
    for cfg_name, cfg in configs.items():
        ndcgs, recalls, mrrs = [], [], []
        for q in queries:
            qid = int(q["id"])
            gmap = labels_by_query.get(qid, {})
            if not gmap:
                continue
            hits = await hybrid_search(
                conn=conn,
                query=q["text"],
                user_skills=cfg["skills"],
                top_k=20,
                use_rerank=cfg["use_rerank"],
            )
            ranked_ids = [int(h["job_id"]) for h in hits]
            ndcgs.append(ndcg_at_k(ranked_ids, gmap, 10))
            recalls.append(recall_at_k(ranked_ids, gmap, 20))
            mrrs.append(mrr_at_k(ranked_ids, gmap, 10))

        report[cfg_name] = {
            "queries_evaluated": len(ndcgs),
            "ndcg_at_10": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0,
            "recall_at_20": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
            "mrr_at_10": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0,
        }

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
            json.dumps({"suite": "retrieval_and_ghost_v1"}),
            json.dumps(summary),
        )
        out_path = Path("evals/results/latest_eval.json")
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
