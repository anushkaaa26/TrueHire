import os
from datetime import date
from uuid import UUID
import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.ghost.features import extract_ghost_features
from app.ghost.scorer import score_features
from app.retrieval.pipeline import SearchFilters, hybrid_search

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

app = FastAPI(title="TrueHire API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FeedbackRequest(BaseModel):
    user_id: UUID
    job_id: int
    event_type: str = Field(..., pattern="^(shown|click|like|dislike|applied)$")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: UUID | None = None
    conv_id: UUID | None = None
    skills: list[str] = Field(default_factory=list)


async def get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(os.getenv("DATABASE_URL", DEFAULT_DB_URL))


@app.get("/health")
async def health() -> dict[str, str]:
    conn = await get_conn()
    try:
        await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    finally:
        await conn.close()


@app.get("/jobs/search")
async def search_jobs_endpoint(
    q: str = Query(..., min_length=1),
    location: str | None = None,
    remote_only: bool = False,
    top_k: int = Query(10, ge=1, le=50),
    rerank: bool = True,
) -> dict:
    conn = await get_conn()
    try:
        results = await hybrid_search(
            conn=conn,
            query=q,
            filters=SearchFilters(location=location, remote_only=remote_only),
            top_k=top_k,
            use_rerank=rerank,
        )
        return {"query": q, "count": len(results), "results": results}
    finally:
        await conn.close()


@app.get("/jobs/{job_id}/trust")
async def job_trust_endpoint(job_id: int) -> dict:
    conn = await get_conn()
    try:
        try:
            feats = await extract_ghost_features(conn, job_id, date.today())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        assessment = score_features(feats)
        await conn.execute(
            """
            INSERT INTO ghost_scores (job_id, scored_at, score, features, model_version)
            VALUES ($1, NOW(), $2, $3::jsonb, $4)
            ON CONFLICT (job_id) DO UPDATE
            SET scored_at = NOW(), score = EXCLUDED.score,
                features = EXCLUDED.features, model_version = EXCLUDED.model_version
            """,
            job_id,
            assessment.trust_score,
            __import__("json").dumps(feats),
            assessment.model_version,
        )
        return {
            "job_id": job_id,
            "ghost_probability": assessment.probability,
            "trust_score": assessment.trust_score,
            "top_signals": assessment.signals,
            "features": feats,
            "model_version": assessment.model_version,
        }
    finally:
        await conn.close()


@app.post("/feedback")
async def feedback_endpoint(payload: FeedbackRequest) -> dict:
    conn = await get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO interactions (user_id, job_id, type)
            VALUES ($1, $2, $3)
            """,
            payload.user_id,
            payload.job_id,
            payload.event_type,
        )
        return {"status": "recorded", "job_id": payload.job_id, "type": payload.event_type}
    finally:
        await conn.close()


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest) -> dict:
    conn = await get_conn()
    try:
        results = await hybrid_search(
            conn=conn,
            query=payload.message,
            user_skills=payload.skills,
            top_k=5,
        )
        cited_ids = [r["job_id"] for r in results]
        return {
            "reply": f"Found {len(results)} matching active roles grounded in Postgres.",
            "cited_job_ids": cited_ids,
            "jobs": results,
        }
    finally:
        await conn.close()
