import asyncio
import csv
import os
import sys
from pathlib import Path
import asyncpg

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"
DEFAULT_CSV_PATH = Path("evals/labels_review.csv")


async def export_csv(csv_path: Path) -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT
                q.id AS query_id,
                q.text AS query_text,
                j.id AS job_id,
                c.name AS company,
                j.title,
                COALESCE(j.location, '') AS location,
                LEFT(COALESCE(j.description, ''), 240) AS snippet,
                l.grade
            FROM eval_labels l
            JOIN eval_queries q ON q.id = l.query_id
            JOIN jobs j ON j.id = l.job_id
            JOIN companies c ON c.id = j.company_id
            ORDER BY q.id, l.grade DESC, j.id
            """
        )
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["query_id", "query_text", "job_id", "company", "title", "location", "snippet", "grade"])
            for r in rows:
                writer.writerow([
                    r["query_id"],
                    r["query_text"],
                    r["job_id"],
                    r["company"],
                    r["title"],
                    r["location"],
                    " ".join((r["snippet"] or "").split()),
                    r["grade"],
                ])
        print(f"Exported {len(rows)} rows to {csv_path}")
    finally:
        await conn.close()


async def import_csv(csv_path: Path) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    updated = 0
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            async with conn.transaction():
                for row in reader:
                    qid = int(row["query_id"])
                    jid = int(row["job_id"])
                    grade = int(row["grade"])
                    if grade not in (0, 1, 2):
                        raise ValueError(f"Invalid grade {grade} for query_id={qid}, job_id={jid} (must be 0, 1, or 2)")
                    await conn.execute(
                        """
                        INSERT INTO eval_labels (query_id, job_id, grade)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (query_id, job_id) DO UPDATE
                        SET grade = EXCLUDED.grade
                        """,
                        qid,
                        jid,
                        grade,
                    )
                    updated += 1
        print(f"Imported/updated {updated} labels from {csv_path}")
    finally:
        await conn.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "export"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CSV_PATH
    if mode == "export":
        asyncio.run(export_csv(target))
    elif mode == "import":
        asyncio.run(import_csv(target))
    else:
        print("Usage: python -m evals.label_csv [export|import] [path/to/file.csv]")
        sys.exit(1)
