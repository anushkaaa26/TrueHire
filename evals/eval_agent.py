import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
import asyncpg
from app.agent.runner import run_agent_turn
from app.agent.schemas import AgentResponse

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

BASE_SCENARIOS: list[dict] = [
    {
        "message": "Find Python FastAPI backend engineer roles",
        "skills": ["python", "fastapi", "postgresql"],
        "yoe": 1.0,
        "run_critic": False,
        "expected_tools": {"search_jobs", "save_pref"},
    },
    {
        "message": "Remote machine learning engineer roles with PyTorch and LLM experience",
        "skills": ["python", "pytorch", "llm", "rag"],
        "yoe": 0.5,
        "run_critic": True,
        "expected_tools": {"search_jobs", "save_pref", "risk_critic"},
    },
    {
        "message": "Frontend React TypeScript engineer in Bengaluru",
        "skills": ["react", "typescript", "next.js"],
        "yoe": 2.0,
        "run_critic": False,
        "expected_tools": {"search_jobs", "save_pref"},
    },
    {
        "message": "Data engineer SQL Docker Kubernetes roles",
        "skills": ["sql", "docker", "kubernetes", "python"],
        "yoe": 1.5,
        "run_critic": True,
        "expected_tools": {"search_jobs", "save_pref", "risk_critic"},
    },
    {
        "message": "Software engineer backend distributed systems",
        "skills": [],
        "yoe": None,
        "run_critic": False,
        "expected_tools": {"search_jobs"},
    },
]


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(round((pct / 100.0) * (len(sorted_vals) - 1))), len(sorted_vals) - 1)
    return round(sorted_vals[idx], 2)


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)

    # Expand 5 base scenarios x 10 variations = 50 scripted agent runs
    scripted_runs: list[dict] = []
    suffixes = ["", " startup", " remote", " india", " senior", " junior", " cloud", " api", " platform", " ai"]
    for suf in suffixes:
        for sc in BASE_SCENARIOS:
            scripted_runs.append({**sc, "message": f"{sc['message']}{suf}".strip()})

    latencies_ms: list[float] = []
    schema_valid_count = 0
    tool_correct_count = 0
    grounded_count = 0

    try:
        valid_ids_rows = await conn.fetch("SELECT id FROM jobs")
        all_db_job_ids = {int(r["id"]) for r in valid_ids_rows}

        for idx, case in enumerate(scripted_runs, start=1):
            t0 = time.perf_counter()
            resp = await run_agent_turn(
                conn=conn,
                message=case["message"],
                user_skills=case["skills"],
                yoe=case["yoe"],
                run_critic=case["run_critic"],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(elapsed_ms)

            # 1. Schema validity check
            if isinstance(resp, AgentResponse):
                AgentResponse.model_validate(resp.model_dump())
                schema_valid_count += 1

            # 2. Tool-call correctness check
            called_tools = {step["tool"] for step in resp.tool_trace}
            if case["expected_tools"].issubset(called_tools):
                tool_correct_count += 1

            # 3. Groundedness check (every cited ID must exist in DB tool output)
            if all(jid in all_db_job_ids for jid in resp.cited_job_ids):
                grounded_count += 1

        latencies_sorted = sorted(latencies_ms)
        total = len(scripted_runs)
        report = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "conversations_evaluated": total,
            "tool_call_correctness_rate": round(tool_correct_count / total, 4),
            "schema_validity_rate": round(schema_valid_count / total, 4),
            "groundedness_rate": round(grounded_count / total, 4),
            "latency_ms": {
                "p50": _percentile(latencies_sorted, 50),
                "p95": _percentile(latencies_sorted, 95),
                "mean": round(statistics.mean(latencies_sorted), 2) if latencies_sorted else 0.0,
            },
        }

        out_path = Path("evals/results/latest_agent_eval.json")
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
