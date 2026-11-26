import asyncio
import os
import sys
import asyncpg
from evals.run_eval import BM25_ONLY_SQL, DENSE_ONLY_SQL, ndcg_at_k
from app.ingestion.embedder import embed_texts, format_pgvector
from app.retrieval.pipeline import hybrid_search

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"


async def analyze_failures(top_n_queries: int = 5) -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)

    try:
        queries = await conn.fetch("SELECT id, text FROM eval_queries ORDER BY id")
        label_rows = await conn.fetch("SELECT query_id, job_id, grade FROM eval_labels")

        labels_by_q: dict[int, dict[int, int]] = {}
        for r in label_rows:
            labels_by_q.setdefault(int(r["query_id"]), {})[int(r["job_id"])] = int(r["grade"])

        q_texts = [q["text"] for q in queries]
        q_vecs = embed_texts(q_texts) if q_texts else []
        vec_map = {int(q["id"]): format_pgvector(v) for q, v in zip(queries, q_vecs)}

        scored_queries: list[dict] = []

        for q in queries:
            qid = int(q["id"])
            gmap = labels_by_q.get(qid, {})
            relevant_ids = {jid for jid, g in gmap.items() if g >= 1}
            if not relevant_ids:
                continue

            hits = await hybrid_search(conn=conn, query=q["text"], top_k=10, use_rerank=True)
            ranked_10 = [int(h["job_id"]) for h in hits]
            score = ndcg_at_k(ranked_10, gmap, 10)

            bm25_rows = await conn.fetch(BM25_ONLY_SQL, q["text"], 50)
            dense_rows = await conn.fetch(DENSE_ONLY_SQL, vec_map[qid], 50)
            bm25_ranks = {int(r["job_id"]): idx + 1 for idx, r in enumerate(bm25_rows)}
            dense_ranks = {int(r["job_id"]): idx + 1 for idx, r in enumerate(dense_rows)}

            missed_ids = [
                jid for jid, g in sorted(gmap.items(), key=lambda kv: kv[1], reverse=True)
                if g >= 1 and jid not in set(ranked_10)
            ]

            missed_details: list[dict] = []
            if missed_ids:
                job_rows = await conn.fetch(
                    """
                    SELECT j.id, j.title, COALESCE(j.location, '') AS location, j.is_active, c.name AS company
                    FROM jobs j
                    JOIN companies c ON c.id = j.company_id
                    WHERE j.id = ANY($1::bigint[])
                    """,
                    missed_ids[:5],
                )
                by_id = {int(r["id"]): r for r in job_rows}
                for jid in missed_ids[:5]:
                    jr = by_id.get(jid)
                    if not jr:
                        continue
                    missed_details.append(
                        {
                            "job_id": jid,
                            "grade": gmap[jid],
                            "company": jr["company"],
                            "title": jr["title"],
                            "location": jr["location"],
                            "active": jr["is_active"],
                            "bm25_rank": bm25_ranks.get(jid),
                            "dense_rank": dense_ranks.get(jid),
                        }
                    )

            scored_queries.append(
                {
                    "query_id": qid,
                    "query": q["text"],
                    "ndcg_at_10": round(score, 4),
                    "missed": missed_details,
                }
            )

        scored_queries.sort(key=lambda item: item["ndcg_at_10"])
        print(f"\n=== Top {top_n_queries} Lowest nDCG@10 Queries (Failure Analysis) ===\n")

        for item in scored_queries[:top_n_queries]:
            print(f"[Q#{item['query_id']}] nDCG@10={item['ndcg_at_10']:.4f} | \"{item['query']}\"")
            if not item["missed"]:
                print("  - All labeled relevant jobs appeared in top 10 (low score due to ranking order).")
            for m in item["missed"]:
                print(
                    f"  - Missed Job #{m['job_id']} (grade={m['grade']}, active={m['active']}): "
                    f"{m['title']} @ {m['company']} [{m['location'] or 'N/A'}] "
                    f"| bm25_rank={m['bm25_rank']} dense_rank={m['dense_rank']}"
                )
            print()
    finally:
        await conn.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    asyncio.run(analyze_failures(n))
