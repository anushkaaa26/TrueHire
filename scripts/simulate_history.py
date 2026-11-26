"""Simulate multi-day job snapshots and lifecycle events to test ghost scoring."""

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"


async def _insert_snapshot(
conn: asyncpg.Connection,
job_id: int,
seen_on: date,
content_hash: str,
title: str,
active: bool = True,
) -> None:
padded_hash = (content_hash or "").ljust(64, "0")[:64]
await conn.execute(
    """
    INSERT INTO job_snapshots (job_id, seen_on, content_hash, title, active)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (job_id, seen_on) DO NOTHING
    """,
    job_id,
    seen_on,
    padded_hash,
    title,
    active,
)


async def _insert_event(
conn: asyncpg.Connection,
job_id: int,
event_type: str,
occurred_on: date,
) -> None:
ts = datetime.combine(occurred_on, datetime.min.time(), tzinfo=timezone.utc)
await conn.execute(
    """
    INSERT INTO job_events (job_id, event_type, at)
    VALUES ($1, $2, $3)
    """,
    job_id,
    event_type,
    ts,
)


async def _upsert_ghost_score(
conn: asyncpg.Connection,
job_id: int,
ghost_probability: float,
features: dict[str, Any],
model_version: str = "simulated_v1",
) -> None:
await conn.execute(
    """
    INSERT INTO ghost_scores (job_id, scored_at, score, features, model_version)
    VALUES ($1, $2, $3, $4::jsonb, $5)
    ON CONFLICT (job_id) DO UPDATE
    SET scored_at = EXCLUDED.scored_at,
        score = EXCLUDED.score,
        features = EXCLUDED.features,
        model_version = EXCLUDED.model_version
    """,
    job_id,
    datetime.now(timezone.utc),
    round(ghost_probability, 4),
    json.dumps(features),
    model_version,
)


async def simulate(limit_per_pattern: int = 8) -> None:
db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
conn = await asyncpg.connect(db_url)

try:
    rows = await conn.fetch(
        """
        SELECT
            id,
            COALESCE(title, '') AS title,
            COALESCE(
                NULLIF(content_hash, ''),
                md5(COALESCE(title, '') || COALESCE(description, ''))
            ) AS content_hash
        FROM jobs
        ORDER BY id ASC
        LIMIT $1
        """,
        limit_per_pattern * 3,
    )

    if not rows:
        print("No rows found in `jobs`. Run `python -m app.ingestion.run_daily` first.")
        return

    today = date.today()
    stale_group = rows[0:limit_per_pattern]
    repost_group = rows[limit_per_pattern : limit_per_pattern * 2]
    edited_group = rows[limit_per_pattern * 2 : limit_per_pattern * 3]

    sample_ids: list[tuple[int, str, float]] = []

    # 1. Stale long-running roles (45 days of snapshots, no edits)
    for r in stale_group:
        jid = int(r["id"])
        chash = str(r["content_hash"])
        for offset in range(45, 0, -3):
            await _insert_snapshot(conn, jid, today - timedelta(days=offset), chash, r["title"], True)
        await _insert_event(conn, jid, "appeared", today - timedelta(days=45))

        ghost_p = 0.78
        await _upsert_ghost_score(
            conn,
            jid,
            ghost_p,
            {
                "reposts_90d": 0.0,
                "days_vs_median_ratio": 2.4,
                "edit_count": 0.0,
                "stale_no_edits": 1.0,
                "top_signals": [
                    {"signal": "stale_no_edits", "weight_contribution": 0.42, "raw_value": 45.0},
                    {"signal": "days_vs_median_ratio", "weight_contribution": 0.36, "raw_value": 2.4},
                ],
            },
        )
        sample_ids.append((jid, "stale_long_lived", ghost_p))

    # 2. Repost / reappearance churn roles (appeared -> disappeared -> reappeared twice in 90d)
    for r in repost_group:
        jid = int(r["id"])
        chash = str(r["content_hash"])
        for offset in [75, 70, 65, 40, 35, 12, 6, 2]:
            await _insert_snapshot(conn, jid, today - timedelta(days=offset), chash, r["title"], True)

        for ev_type, off in [
            ("appeared", 75),
            ("disappeared", 62),
            ("reappeared", 40),
            ("disappeared", 30),
            ("reappeared", 12),
        ]:
            await _insert_event(conn, jid, ev_type, today - timedelta(days=off))

        ghost_p = 0.86
        await _upsert_ghost_score(
            conn,
            jid,
            ghost_p,
            {
                "reposts_90d": 2.0,
                "days_vs_median_ratio": 2.1,
                "edit_count": 0.0,
                "stale_no_edits": 0.0,
                "top_signals": [
                    {"signal": "reposts_90d", "weight_contribution": 0.56, "raw_value": 2.0},
                    {"signal": "days_vs_median_ratio", "weight_contribution": 0.30, "raw_value": 2.1},
                ],
            },
        )
        sample_ids.append((jid, "repost_churn", ghost_p))

    # 3. Healthy active roles with edits and recent appearance
    for idx, r in enumerate(edited_group):
        jid = int(r["id"])
        chash = str(r["content_hash"])
        for offset in [8, 5, 2]:
            variant_hash = f"{chash[:56]}{idx:02d}{offset:06d}"
            await _insert_snapshot(conn, jid, today - timedelta(days=offset), variant_hash, r["title"], True)

        await _insert_event(conn, jid, "appeared", today - timedelta(days=8))
        await _insert_event(conn, jid, "edited", today - timedelta(days=3))

        ghost_p = 0.14
        await _upsert_ghost_score(
            conn,
            jid,
            ghost_p,
            {
                "reposts_90d": 0.0,
                "days_vs_median_ratio": 0.4,
                "edit_count": 1.0,
                "stale_no_edits": 0.0,
                "top_signals": [
                    {"signal": "recent_fresh_listing", "weight_contribution": 0.14, "raw_value": 1.0},
                ],
            },
        )
        sample_ids.append((jid, "healthy_active", ghost_p))

    total_snaps = await conn.fetchval("SELECT COUNT(*) FROM job_snapshots")
    total_events = await conn.fetchval("SELECT COUNT(*) FROM job_events")
    total_scores = await conn.fetchval("SELECT COUNT(*) FROM ghost_scores")
    print(f"DB totals -> job_snapshots: {total_snaps}, job_events: {total_events}, ghost_scores: {total_scores}")
    print("\nSample simulated jobs:")
    for jid, pattern, gp in sample_ids[:9]:
        print(f"  - Job #{jid:4d} | pattern={pattern:16s} | ghost_p={gp:.2f} | trust={1.0 - gp:.2f}")
finally:
    await conn.close()


if __name__ == "__main__":
asyncio.run(simulate())
