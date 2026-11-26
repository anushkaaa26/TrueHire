import asyncio
import os
import re
import asyncpg

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

STARTER_QUERIES: list[tuple[str, list[str]]] = [
    ("python backend engineer fastapi postgresql", ["python", "backend", "fastapi", "postgresql", "api"]),
    ("machine learning engineer llm rag pytorch", ["machine learning", "ml", "llm", "rag", "pytorch", "ai"]),
    ("data engineer sql airflow spark warehouse", ["data engineer", "sql", "airflow", "spark", "warehouse", "etl"]),
    ("remote frontend react typescript nextjs", ["frontend", "react", "typescript", "next.js", "nextjs", "remote"]),
    ("cloud devops kubernetes docker aws terraform", ["devops", "kubernetes", "docker", "aws", "cloud", "terraform"]),
    ("software engineer india bengaluru backend", ["backend", "engineer", "bengaluru", "bangalore", "india"]),
    ("full stack engineer python react", ["full stack", "fullstack", "python", "react", "typescript"]),
    ("distributed systems golang rust backend", ["distributed", "golang", "go", "rust", "systems"]),
    ("applied scientist computer vision deep learning", ["computer vision", "vision", "deep learning", "ml", "scientist"]),
    ("site reliability engineer observability prometheus", ["sre", "reliability", "observability", "monitoring", "incident"]),
    ("analytics engineer dbt snowflake sql", ["analytics", "dbt", "snowflake", "sql", "bi"]),
    ("product engineer remote startup", ["product engineer", "remote", "full stack", "frontend", "backend"]),
    ("security engineer cloud application security", ["security", "appsec", "cloud security", "iam", "vulnerability"]),
    ("platform engineer developer experience internal tools", ["platform", "developer experience", "dx", "internal", "infrastructure"]),
    ("java spring boot microservices backend", ["java", "spring", "microservices", "backend", "kafka"]),
    ("data scientist experimentation causal inference ab testing", ["data scientist", "experimentation", "causal", "statistics", "ab test"]),
    ("nlp engineer search retrieval embeddings", ["nlp", "search", "retrieval", "embeddings", "vector"]),
    ("mobile engineer android ios react native", ["mobile", "android", "ios", "react native", "flutter"]),
    ("intern software engineer python ml", ["intern", "internship", "graduate", "junior", "python", "ml"]),
    ("remote india engineering role", ["remote", "india", "bengaluru", "bangalore", "hyderabad", "pune"]),
]


def _score_job_against_keywords(title: str, location: str, description: str, keywords: list[str]) -> int:
    t = (title or "").lower()
    loc = (location or "").lower()
    desc = (description or "").lower()

    title_hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", t))
    loc_hits = sum(1 for kw in keywords if kw in loc)
    desc_hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", desc))

    if title_hits >= 2 or (title_hits >= 1 and (loc_hits >= 1 or desc_hits >= 2)):
        return 2
    if title_hits >= 1 or loc_hits >= 1 or desc_hits >= 2:
        return 1
    return 0


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)

    try:
        job_count = await conn.fetchval("SELECT COUNT(*) FROM jobs")
        if job_count == 0:
            print("No jobs in database yet. Run `python -m app.ingestion.run_daily` first.")
            return

        jobs = await conn.fetch(
            """
            SELECT id, title, COALESCE(location, '') AS location, COALESCE(description, '') AS description
            FROM jobs
            ORDER BY id
            LIMIT 400
            """
        )

        seeded_queries = 0
        seeded_labels = 0

        async with conn.transaction():
            for q_text, keywords in STARTER_QUERIES:
                q_id = await conn.fetchval(
                    "SELECT id FROM eval_queries WHERE text = $1",
                    q_text,
                )
                if q_id is None:
                    q_id = await conn.fetchval(
                        "INSERT INTO eval_queries (text) VALUES ($1) RETURNING id",
                        q_text,
                    )
                    seeded_queries += 1

                scored: list[tuple[int, int]] = []
                for j in jobs:
                    g = _score_job_against_keywords(j["title"], j["location"], j["description"], keywords)
                    if g > 0:
                        scored.append((int(j["id"]), g))

                # Keep top 15 graded jobs per query so label sets stay balanced and fast to review
                scored.sort(key=lambda item: item[1], reverse=True)
                for job_id, grade in scored[:15]:
                    await conn.execute(
                        """
                        INSERT INTO eval_labels (query_id, job_id, grade)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (query_id, job_id) DO UPDATE
                        SET grade = EXCLUDED.grade
                        """,
                        int(q_id),
                        job_id,
                        grade,
                    )
                    seeded_labels += 1

        total_q = await conn.fetchval("SELECT COUNT(*) FROM eval_queries")
        total_l = await conn.fetchval("SELECT COUNT(*) FROM eval_labels")
        print(f"Added {seeded_queries} new queries, upserted {seeded_labels} label rows.")
        print(f"Totals in DB -> eval_queries: {total_q}, eval_labels: {total_l}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
