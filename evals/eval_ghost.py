import asyncio
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
import asyncpg
from app.ghost.features import extract_ghost_features
from app.ghost.scorer import score_features

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"
DEFAULT_GHOST_CSV = Path("evals/ghost_labels_review.csv")


async def export_ghost_sample(csv_path: Path, limit: int = 150) -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    today = date.today()

    try:
        rows = await conn.fetch(
            """
            SELECT j.id AS job_id, c.name AS company, j.title, COALESCE(j.location, '') AS location,
                   j.first_seen, j.last_seen, j.is_active
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            ORDER BY j.id
            LIMIT $1
            """,
            limit,
        )
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "job_id",
                "company",
                "title",
                "location",
                "first_seen",
                "last_seen",
                "is_active",
                "pred_ghost_prob",
                "ghost_label",
                "labeler_2",
                "notes",
            ])
            for r in rows:
                jid = int(r["job_id"])
                feats = await extract_ghost_features(conn, jid, today)
                assessment = score_features(feats)
                writer.writerow([
                    jid,
                    r["company"],
                    r["title"],
                    r["location"],
                    r["first_seen"].isoformat(),
                    r["last_seen"].isoformat(),
                    int(bool(r["is_active"])),
                    assessment.probability,
                    "",
                    "",
                    "proxy_label_pending",
                ])
        print(f"Exported {len(rows)} jobs to {csv_path} for hand-labeling (fill ghost_label with 0 or 1).")
    finally:
        await conn.close()


def _agreement_metrics(pairs: list[tuple[int, int]]) -> dict[str, float | int]:
    if not pairs:
        return {"n_compared": 0, "raw_agreement": 0.0, "cohens_kappa": 0.0}
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    p0 = agree / n
    a1 = sum(1 for a, _ in pairs if a == 1) / n
    a0 = 1.0 - a1
    b1 = sum(1 for _, b in pairs if b == 1) / n
    b0 = 1.0 - b1
    pe = (a1 * b1) + (a0 * b0)
    kappa = (p0 - pe) / (1.0 - pe) if pe < 1.0 else 1.0
    return {
        "n_compared": n,
        "raw_agreement": round(p0, 4),
        "cohens_kappa": round(kappa, 4),
    }


async def evaluate_ghost_csv(csv_path: Path, threshold: float = 0.5) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"Ghost label CSV not found: {csv_path}. Run `export` first.")

    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    today = date.today()

    tp = fp = fn = tn = 0
    labeled_count = 0
    labeler_pairs: list[tuple[int, int]] = []
    per_row_results: list[dict] = []

    try:
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_label = (row.get("ghost_label") or "").strip()
                if raw_label not in ("0", "1"):
                    continue
                y_true = int(raw_label)
                jid = int(row["job_id"])
                labeled_count += 1

                l2_raw = (row.get("labeler_2") or "").strip()
                if l2_raw in ("0", "1"):
                    labeler_pairs.append((y_true, int(l2_raw)))

                try:
                    feats = await extract_ghost_features(conn, jid, today)
                    assessment = score_features(feats)
                    prob = assessment.probability
                except ValueError:
                    prob = float(row.get("pred_ghost_prob") or 0.0)

                y_pred = 1 if prob >= threshold else 0
                if y_pred == 1 and y_true == 1:
                    tp += 1
                elif y_pred == 1 and y_true == 0:
                    fp += 1
                elif y_pred == 0 and y_true == 1:
                    fn += 1
                else:
                    tn += 1

                per_row_results.append({"job_id": jid, "y_true": y_true, "y_pred": y_pred, "prob": prob})

        if labeled_count == 0:
            print(f"No rows with ghost_label in {{0, 1}} found in {csv_path}. Edit the CSV first and re-run.")
            return

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        accuracy = (tp + tn) / labeled_count

        metrics = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "label_note": "Hand-labeled proxy labels; not ground-truth internal ATS hiring intent.",
            "threshold": threshold,
            "labeled_samples": labeled_count,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "inter_labeler_agreement": _agreement_metrics(labeler_pairs),
        }

        out_path = Path("evals/results/latest_ghost_eval.json")
        out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        print("\n=== Ghost Scorer Evaluation (Proxy Hand Labels) ===")
        print(f"Labeled rows : {labeled_count} (threshold={threshold})")
        print(f"Precision    : {metrics['precision']:.4f}")
        print(f"Recall       : {metrics['recall']:.4f}")
        print(f"F1           : {metrics['f1']:.4f}")
        print(f"Accuracy     : {metrics['accuracy']:.4f}")
        print(f"Confusion    : TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        if labeler_pairs:
            print(f"Inter-labeler: {metrics['inter_labeler_agreement']}")
        print(f"Saved report -> {out_path}\n")
    finally:
        await conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    csv_arg = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_GHOST_CSV
    if cmd == "export":
        lim = int(sys.argv[3]) if len(sys.argv) > 3 else 150
        asyncio.run(export_ghost_sample(csv_arg, lim))
    elif cmd == "eval":
        thresh = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
        asyncio.run(evaluate_ghost_csv(csv_arg, thresh))
    else:
        print("Usage: python -m evals.eval_ghost [export|eval] [csv_path] [limit_or_threshold]")
        sys.exit(1)
