from datetime import date
import asyncpg
import httpx
from app.ingestion.connectors import fetch_greenhouse, fetch_lever
from app.ingestion.schemas import NormalizedJob

FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
}


async def ingest_company(
    conn: asyncpg.Connection,
    client: httpx.AsyncClient,
    company: asyncpg.Record,
    today: date,
) -> list[int]:
    fetcher = FETCHERS.get(company["ats_type"])
    if not fetcher:
        return []

    fetched_jobs: list[NormalizedJob] = await fetcher(client, company["board_slug"])
    fetched_map = {j.external_id: j for j in fetched_jobs}

    existing_rows = await conn.fetch(
        """
        SELECT id, external_id, content_hash, is_active
        FROM jobs
        WHERE company_id = $1 AND source = $2
        """,
        company["id"],
        company["ats_type"],
    )
    existing_map = {r["external_id"]: r for r in existing_rows}
    jobs_to_embed: list[int] = []

    async with conn.transaction():
        for ext_id, job in fetched_map.items():
            c_hash = job.content_hash
            existing = existing_map.get(ext_id)

            if existing is None:
                job_id = await conn.fetchval(
                    """
                    INSERT INTO jobs (company_id, external_id, source, title, location, is_remote,
                                      description, apply_url, content_hash, first_seen, last_seen, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, TRUE)
                    RETURNING id
                    """,
                    company["id"], ext_id, job.source, job.title, job.location,
                    job.is_remote, job.description, job.apply_url, c_hash, today,
                )
                await conn.execute(
                    "INSERT INTO job_events (job_id, event_type) VALUES ($1, 'appeared')",
                    job_id,
                )
                jobs_to_embed.append(job_id)
            else:
                job_id = existing["id"]
                if not existing["is_active"]:
                    await conn.execute(
                        "INSERT INTO job_events (job_id, event_type) VALUES ($1, 'reappeared')",
                        job_id,
                    )
                if existing["content_hash"] != c_hash:
                    await conn.execute(
                        "INSERT INTO job_events (job_id, event_type) VALUES ($1, 'edited')",
                        job_id,
                    )
                    jobs_to_embed.append(job_id)

                await conn.execute(
                    """
                    UPDATE jobs
                    SET title = $1, location = $2, is_remote = $3, description = $4,
                        apply_url = $5, content_hash = $6, last_seen = $7, is_active = TRUE
                    WHERE id = $8
                    """,
                    job.title, job.location, job.is_remote, job.description,
                    job.apply_url, c_hash, today, job_id,
                )

            await conn.execute(
                """
                INSERT INTO job_snapshots (job_id, seen_on, content_hash, title, active)
                VALUES ($1, $2, $3, $4, TRUE)
                ON CONFLICT (job_id, seen_on) DO UPDATE
                SET content_hash = EXCLUDED.content_hash, title = EXCLUDED.title, active = TRUE
                """,
                job_id, today, c_hash, job.title,
            )

        for ext_id, existing in existing_map.items():
            if existing["is_active"] and ext_id not in fetched_map:
                job_id = existing["id"]
                await conn.execute("UPDATE jobs SET is_active = FALSE WHERE id = $1", job_id)
                await conn.execute(
                    "INSERT INTO job_events (job_id, event_type) VALUES ($1, 'disappeared')",
                    job_id,
                )

    return jobs_to_embed
