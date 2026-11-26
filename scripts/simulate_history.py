"""Simulate multi-day job snapshots and lifecycle events to test ghost scoring."""

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"


async def _table_columns(conn: asyncpg.Connection, table_name: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    return {r["column_name"] for r in rows}


async def _insert_snapshot(
    conn: asyncpg.Connection,
    snap_cols: set[str],
    job_id: int,
    seen_on: date,
    content_hash: str,
    title: str,
    location: str,
    is_active: bool = True,
) -> None:
    cols: list[str] = []
    vals: list[Any] = []

    if "job_id" in snap_cols:
        cols.append("job_id")
        vals.append(job_id)
    if "seen_on" in snap_cols:
        cols.append("seen_on")
        vals.append(seen_on)
    if "content_hash" in snap_cols:
        cols.append("content_hash")
        vals.append(content_hash)
    if "title" in snap_cols:
        cols.append("title")
        vals.append(title)
    if "location" in snap_cols:
        cols.append("location")
        vals.append(location)
    if "is_active" in snap_cols:
        cols.append("is_active")
        vals.append(is_active)
    if "captured_at" in snap_cols:
        cols.append("captured_at")
        vals.append(datetime.combine(seen_on, datetime.min.time(), tzinfo=timezone.utc))

    if not cols:
        return

    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    col_sql = ", ".join(cols)

    conflict_sql = ""
    if "job_id" in snap_cols and "seen_on" in snap_cols:
        conflict_sql = " ON CONFLICT (job_id, seen_on) DO NOTHING"

    await conn.execute(
        f"INSERT INTO job_snapshots ({col_sql}) VALUES ({placeholders}){conflict_sql}",
        *vals,
    )


async def _insert_event(
    conn: asyncpg.Connection,
    event_cols: set[str],
    job_id: int,
    event_type: str,
    occurred_on: date,
    meta: dict[str, Any],
) -> None:
    cols: list[str] = []
    vals: list[Any] = []

    if "job_id" in event_cols:
        cols.append("job_id")
        vals.append(job_id)
    if "event_type" in event_cols:
        cols.append("event_type")
        vals.append(event_type)
    elif "kind" in event_cols:
        cols.append("kind")
        vals.append(event_type)

    if "occurred_on" in event_cols:
        cols.append("occurred_on")
        vals.append(occurred_on)
    elif "seen_on" in event_cols:
        cols.append("seen_on")
        vals.append(occurred_on)

    if "occurred_at" in event_cols:
        cols.append("occurred_at")
        vals.append(datetime.combine(occurred_on, datetime.min.time(), tzinfo=timezone.utc))
    elif "created_at" in event_cols:
        cols.append("created_at")
        vals.append(datetime.combine(occurred_on, datetime.min.time(), tzinfo=timezone.utc))

    if "metadata" in event_cols:
        cols.append("metadata")
        vals.append(json.dumps(meta))
    elif "details" in event_cols:
        cols.append("details")
        vals.append(json.dumps(meta))

    if not cols:
        return

    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    col_sql = ", ".join(cols)
    await conn.execute(
        f"INSERT INTO job_events ({col_sql}) VALUES ({placeholders})",
        *vals,
    )


async def _upsert_ghost_score(
    conn: asyncpg.Connection,
    ghost_cols: set[str],
    job_id: int,
    ghost_probability: float,
    trust_score: float,
    signals: list[dict[str, Any]],
    features: dict[str, float],
) -> None:
    if not ghost_cols or "job_id" not in ghost_cols:
        return

    cols: list[str] = ["job_id"]
    vals: list[Any] = [job_id]
    updates: list[str] = []

    def add_col(name: str, val: Any) -> None:
        if name in ghost_cols:
            cols.append(name)
            vals.append(val)
            updates.append(f"{name} = EXCLUDED.{name}")

    add_col("ghost_probability", round(ghost_probability, 4))
    add_col("trust_score", round(trust_score, 4))
    add_col("top_signals", json.dumps(signals))
    add_col("signals", json.dumps(signals))
    add_col("features", json.dumps(features))
    add_col("model_version", "simulated_v1")
    add_col("scored_at", datetime.now(timezone.utc))
    add_col("updated_at", datetime.now(timezone.utc))

    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    col_sql = ", ".join(cols)
    update_sql = ", ".join(updates) if updates else "job_id = EXCLUDED.job_id"

    await conn.execute(
        f"""
        INSERT INTO ghost_scores ({col_sql})
        VALUES ({placeholders})
        ON CONFLICT (job_id) DO UPDATE SET {update_sql}
        """,
        *vals,
    )


async def simulate(limit_per_pattern: int = 8) -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)

    try:
        snap_cols = await _table_columns(conn, "job_snapshots")
        event_cols = await _table_columns(conn, "job_events")
        ghost_cols = await _table_columns(conn, "ghost_scores")

        rows = await conn.fetch(
            """
            SELECT id, title, location, COALESCE(content_hash, md5(COALESCE(title, '') || COALESCE(description, ''))) AS content_hash
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

        inserted_snaps = 0
        inserted_events = 0
        sample_ids: list[tuple[int, str, float]] = []

        # 1. Stale long-running roles (seen daily for 45 days with no edits)
        for r in stale_group:
            jid = int(r["id"])
            chash = str(r["content_hash"])
            for offset in range(45, 0, -3):
                d = today - timedelta(days=offset)
                await _insert_snapshot(conn, snap_cols, jid, d, chash, r["title"] or "", r["location"] or "", True)
                inserted_snaps += 1
            await _insert_event(conn, event_cols, jid, "appeared", today - timedelta(days=45), {"sim": True})
            inserted_events += 1

            ghost_p = 0.78
            await _upsert_ghost_score(
                conn,
                ghost_cols,
                jid,
                ghost_p,
                1.0 - ghost_p,
                [
                    {"signal": "stale_no_edits", "weight_contribution": 0.42, "raw_value": 45.0},
                    {"signal": "days_vs_median_ratio", "weight_contribution": 0.36, "raw_value": 2.4},
                ],
                {"reposts_90d": 0.0, "days_vs_median_ratio": 2.4, "edit_count": 0.0, "stale_no_edits": 1.0},
            )
            sample_ids.append((jid, "stale_long_lived", ghost_p))

        # 2. Repost / reappearance churn roles (appeared -> disappeared -> reappeared twice in 90d)
        for r in repost_group:
            jid = int(r["id"])
            chash = str(r["content_hash"])
            for offset in [75, 70, 65, 40, 35, 12, 6, 2]:
                d = today - timedelta(days=offset)
                await _insert_snapshot(conn, snap_cols, jid, d, chash, r["title"] or "", r["location"] or "", True)
                inserted_snaps += 1

            for ev_type, off in [
                ("appeared", 75),
                ("disappeared", 62),
                ("reappeared", 40),
                ("disappeared", 30),
                ("reappeared", 12),
            ]:
                await _insert_event(conn, event_cols, jid, ev_type, today - timedelta(days=off), {"sim": True})
                inserted_events += 1

            ghost_p = 0.86
            await _upsert_ghost_score(
                conn,
                ghost_cols,
                jid,
                ghost_p,
                1.0 - ghost_p,
                [
                    {"signal": "reposts_90d", "weight_contribution": 0.56, "raw_value": 2.0},
                    {"signal": "days_vs_median_ratio", "weight_contribution": 0.30, "raw_value": 2.1},
                ],
                {"reposts_90d": 2.0, "days_vs_median_ratio": 2.1, "edit_count": 0.0, "stale_no_edits": 0.0},
            )
            sample_ids.append((jid, "repost_churn", ghost_p))

        # 3. Healthy active roles with minor edits and recent appearance
        for r in edited_group:
            jid = int(r["id"])
            chash = str(r["content_hash"])
            for offset in [8, 5, 2]:
                d = today - timedelta(days=offset)
                await _insert_snapshot(
                    conn,
                    snap_cols,
                    jid,
                    d,
                    f"{chash[:12]}_{offset}",
                    r["title"] or "",
                    r["location"] or "",
                    True,
                )
                inserted_snaps += 1

            await _insert_event(conn, event_cols, jid, "appeared", today - timedelta(days=8), {"sim": True})
            await _insert_event(conn, event_cols, jid, "edited", today - timedelta(days=3), {"sim": True})
            inserted_events += 2

            ghost_p = 0.14
            await _upsert_ghost_score(
                conn,
                ghost_cols,
                jid,
                ghost_p,
                1.0 - ghost_p,
                [{"signal": "recent_fresh_listing", "weight_contribution": 0.14, "raw_value": 1.0}],
                {"reposts_90d": 0.0, "days_vs_median_ratio": 0.4, "edit_count": 1.0, "stale_no_edits": 0.0},
            )
            sample_ids.append((jid, "healthy_active", ghost_p))

        total_snaps = await conn.fetchval("SELECT COUNT(*) FROM job_snapshots")
        total_events = await conn.fetchval("SELECT COUNT(*) FROM job_events")
        print(f"Inserted ~{inserted_snaps} historical snapshots and ~{inserted_events} lifecycle events.")
        print(f"DB totals -> job_snapshots: {total_snaps}, job_events: {total_events}")
        print("\nSample simulated jobs (try inspecting these in the UI or via /jobs/<id>/trust):")
        for jid, pattern, gp in sample_ids[:9]:
            print(f"  - Job #{jid:4d} | pattern={pattern:16s} | ghost_p={gp:.2f} | trust={1.0 - gp:.2f}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(simulate())
