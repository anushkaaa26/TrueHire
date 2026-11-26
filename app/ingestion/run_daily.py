import asyncio
import os
from datetime import date
import asyncpg
import httpx
from app.ingestion.embedder import embed_texts, format_pgvector
from app.ingestion.worker import ingest_company

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

SEED_COMPANIES = [
    ("Postman", "greenhouse", "postman", "postman.com"),
    ("Razorpay", "greenhouse", "razorpay", "razorpay.com"),
    ("Groww", "greenhouse", "groww", "groww.in"),
    ("BrowserStack", "lever", "browserstack", "browserstack.com"),
]


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    today = date.today()
    conn = await asyncpg.connect(db_url)

    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM companies")
        if count == 0:
            for name, ats_type, slug, domain in SEED_COMPANIES:
                await conn.execute(
                    """
                    INSERT INTO companies (name, ats_type, board_slug, domain)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (ats_type, board_slug) DO NOTHING
                    """,
                    name, ats_type, slug, domain,
                )

        companies = await conn.fetch("SELECT id, name, ats_type, board_slug, domain FROM companies ORDER BY id")
        to_embed_ids: list[int] = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for comp in companies:
                try:
                    ids = await ingest_company(conn, client, comp, today)
                    to_embed_ids.extend(ids)
                    print(f"[{comp['ats_type']}:{comp['board_slug']}] queued {len(ids)} jobs for embedding")
                except Exception as exc:
                    print(f"[{comp['ats_type']}:{comp['board_slug']}] error: {exc}")

        unique_ids = list(dict.fromkeys(to_embed_ids))
        if unique_ids:
            rows = await conn.fetch(
                "SELECT id, title, location, description FROM jobs WHERE id = ANY($1::bigint[])",
                unique_ids,
            )
            docs = [f"{r['title']} | {r['location'] or ''} | {(r['description'] or '')[:1500]}" for r in rows]
            vectors = embed_texts(docs)
            for row, vec in zip(rows, vectors):
                await conn.execute(
                    "UPDATE jobs SET embedding = $1::vector WHERE id = $2",
                    format_pgvector(vec),
                    row["id"],
                )
            print(f"Embedded {len(rows)} new/edited jobs")

        await conn.execute(
            """
            WITH spans AS (
                SELECT company_id, GREATEST((last_seen - first_seen), 1)::float AS days_open
                FROM jobs
            ),
            meds AS (
                SELECT company_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY days_open) AS med_days
                FROM spans
                GROUP BY company_id
            )
            UPDATE companies c
            SET median_days_open = m.med_days
            FROM meds m
            WHERE c.id = m.company_id
            """
        )
        print(f"Daily ingestion complete for {today}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
