from dataclasses import dataclass
import asyncpg
from app.ingestion.embedder import embed_texts, format_pgvector
from app.retrieval.queries import RRF_HYBRID_SEARCH_SQL


@dataclass
class SearchFilters:
    role: str | None = None
    location: str | None = None
    remote_only: bool = False
    seniority: str | None = None


async def hybrid_search(
    conn: asyncpg.Connection,
    query: str,
    filters: SearchFilters | None = None,
    user_skills: list[str] | None = None,
    rrf_k: int = 60,
    top_k: int = 10,
    use_rerank: bool = True,
) -> list[dict]:
    q_vec = embed_texts([query])[0]
    q_vec_str = format_pgvector(q_vec)

    rows = await conn.fetch(
        RRF_HYBRID_SEARCH_SQL,
        query,
        q_vec_str,
        float(rrf_k),
        30 if use_rerank else top_k,
    )

    skills_set = {s.strip().lower() for s in (user_skills or []) if s.strip()}
    candidates: list[dict] = []

    for idx, r in enumerate(rows):
        title_l = (r["title"] or "").lower()
        loc_l = (r["location"] or "").lower()

        if filters:
            if filters.remote_only and not r["is_remote"]:
                continue
            if filters.location and filters.location.lower() not in loc_l and not r["is_remote"]:
                continue
            if filters.role and filters.role.lower() not in title_l:
                continue

        base_score = float(r["rrf_score"] or 0.0)
        rerank_bonus = (0.015 / (idx + 1)) if use_rerank else 0.0
        skill_overlap = sum(1 for sk in skills_set if sk in title_l) * 0.003

        final_score = round(base_score + rerank_bonus + skill_overlap, 6)
        candidates.append(
            {
                "job_id": int(r["id"]),
                "title": r["title"],
                "company": r["company"],
                "location": r["location"],
                "is_remote": bool(r["is_remote"]),
                "apply_url": r["apply_url"],
                "rrf_score": round(base_score, 6),
                "score": final_score,
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:top_k]
