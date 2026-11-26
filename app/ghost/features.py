import re
from datetime import date
import asyncpg
import numpy as np

TECH_PATTERN = re.compile(
    r"\b(python|java|c\+\+|typescript|javascript|go|rust|sql|postgres|postgresql|"
    r"redis|kafka|docker|kubernetes|aws|gcp|azure|fastapi|django|flask|react|"
    r"next\.?js|pytorch|tensorflow|spark|airflow|dbt|snowflake|llm|rag)\b",
    re.IGNORECASE,
)
TEAM_PATTERN = re.compile(
    r"\b(team|squad|pod|platform|core|infrastructure|growth|payments|data)\b",
    re.IGNORECASE,
)
SALARY_PATTERN = re.compile(
    r"(₹|\$|€|£|\d+\s*(?:lpa|lakhs?|k\b|usd|inr))",
    re.IGNORECASE,
)
DEADLINE_PATTERN = re.compile(
    r"\b(deadline|apply by|closing date|last date|applications close|before\s+\w+\s+\d{1,2})\b",
    re.IGNORECASE,
)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


async def extract_ghost_features(conn: asyncpg.Connection, job_id: int, today: date) -> dict[str, float]:
    job = await conn.fetchrow(
        """
        SELECT j.id, j.company_id, j.title, j.description, j.first_seen, j.last_seen,
               j.embedding::text AS emb_text, c.median_days_open
        FROM jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE j.id = $1
        """,
        job_id,
    )
    if not job:
        raise ValueError(f"Job {job_id} not found")

    counts = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE event_type = 'reappeared' AND at >= NOW() - INTERVAL '90 days'
            )::float AS reposts_90d,
            COUNT(*) FILTER (
                WHERE event_type = 'edited'
            )::float AS edit_count
        FROM job_events
        WHERE job_id = $1
        """,
        job_id,
    )

    cross_board_count = await conn.fetchval(
        """
        SELECT COUNT(*)::float
        FROM jobs
        WHERE id <> $1
          AND company_id = $2
          AND is_active = TRUE
          AND lower(title) = lower($3)
        """,
        job_id,
        job["company_id"],
        job["title"],
    )

    days_open = float(max((job["last_seen"] - job["first_seen"]).days, 1))
    median_open = float(job["median_days_open"] or 30.0)
    days_vs_median_ratio = days_open / max(median_open, 1.0)

    desc = job["description"] or ""
    tech_hits = len(set(m.group(0).lower() for m in TECH_PATTERN.finditer(desc)))
    team_hits = len(TEAM_PATTERN.findall(desc))
    salary_hits = len(SALARY_PATTERN.findall(desc))
    deadline_hits = len(DEADLINE_PATTERN.findall(desc))
    specificity_count = float(tech_hits + team_hits + salary_hits + deadline_hits)

    high_boilerplate_peers = 0.0
    if job["emb_text"]:
        target_vec = np.fromstring(job["emb_text"].strip("[]"), sep=",", dtype=np.float32)
        peer_rows = await conn.fetch(
            """
            SELECT embedding::text AS emb_text
            FROM jobs
            WHERE id <> $1 AND company_id = $2 AND embedding IS NOT NULL
            LIMIT 40
            """,
            job_id,
            job["company_id"],
        )
        for pr in peer_rows:
            peer_vec = np.fromstring(pr["emb_text"].strip("[]"), sep=",", dtype=np.float32)
            if _cosine_sim(target_vec, peer_vec) > 0.95:
                high_boilerplate_peers += 1.0

    edits = float(counts["edit_count"] or 0.0)
    stale_no_edits = 1.0 if (days_open >= 30.0 and edits == 0.0) else 0.0

    return {
        "reposts_90d": float(counts["reposts_90d"] or 0.0),
        "days_vs_median_ratio": round(days_vs_median_ratio, 3),
        "edit_count": edits,
        "stale_no_edits": stale_no_edits,
        "specificity_count": specificity_count,
        "high_boilerplate_peers": high_boilerplate_peers,
        "cross_board_duplicates": float(cross_board_count or 0.0),
    }
