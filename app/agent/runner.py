from datetime import date
from typing import Any
import asyncpg
from pydantic import ValidationError
from app.agent.grounding import enforce_grounded_ids
from app.agent.risk_critic import run_risk_critic
from app.agent.schemas import (
    AgentResponse,
    ExplainFitArgs,
    GetJobArgs,
    RiskCriticArgs,
    SavePrefArgs,
    SearchJobsArgs,
)
from app.ghost.features import extract_ghost_features
from app.ghost.scorer import score_features
from app.retrieval.pipeline import SearchFilters, hybrid_search


def _validate_with_retry(schema_cls: type, payload: dict[str, Any], max_retries: int = 2) -> Any:
    last_err: Exception | None = None
    candidate = dict(payload)
    for _ in range(max_retries + 1):
        try:
            return schema_cls.model_validate(candidate)
        except ValidationError as exc:
            last_err = exc
            candidate = {k: v for k, v in candidate.items() if v is not None}
    raise ValueError(f"Tool schema validation failed for {schema_cls.__name__}: {last_err}")


async def run_agent_turn(
    conn: asyncpg.Connection,
    message: str,
    user_skills: list[str] | None = None,
    yoe: float | None = None,
    requested_job_id: int | None = None,
    run_critic: bool = False,
) -> AgentResponse:
    skills = list(user_skills or [])
    tool_returned_ids: set[int] = set()
    tool_trace: list[dict[str, Any]] = []
    risk_out = None

    search_args = _validate_with_retry(
        SearchJobsArgs,
        {"query": message, "top_k": 5},
    )
    jobs = await hybrid_search(
        conn=conn,
        query=search_args.query,
        filters=SearchFilters(
            role=search_args.role,
            location=search_args.location,
            remote_only=search_args.remote_only,
        ),
        user_skills=skills,
        top_k=search_args.top_k,
    )
    for item in jobs:
        tool_returned_ids.add(int(item["job_id"]))
    tool_trace.append({"tool": "search_jobs", "args": search_args.model_dump(), "count": len(jobs)})

    if skills:
        pref_args = _validate_with_retry(SavePrefArgs, {"skills": skills, "yoe": yoe})
        tool_trace.append({"tool": "save_pref", "args": pref_args.model_dump(), "status": "ok"})

    target_jid = requested_job_id or (int(jobs[0]["job_id"]) if jobs else None)
    if target_jid is not None:
        job_args = _validate_with_retry(GetJobArgs, {"job_id": target_jid})
        row = await conn.fetchrow(
            """
            SELECT j.id, j.title, j.location, j.is_remote, j.apply_url, c.name AS company
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.id = $1
            """,
            job_args.job_id,
        )
        if row:
            tool_returned_ids.add(int(row["id"]))
            feats = await extract_ghost_features(conn, int(row["id"]), date.today())
            trust = score_features(feats)
            fit_args = _validate_with_retry(
                ExplainFitArgs,
                {"job_id": int(row["id"]), "candidate_skills": skills},
            )
            tool_trace.append(
                {
                    "tool": "get_job",
                    "args": job_args.model_dump(),
                    "trust_score": trust.trust_score,
                }
            )
            tool_trace.append(
                {
                    "tool": "explain_fit",
                    "args": fit_args.model_dump(),
                    "matched_skills": skills,
                }
            )

        if run_critic:
            critic_args = _validate_with_retry(
                RiskCriticArgs,
                {"job_id": target_jid, "candidate_skills": skills, "yoe": yoe},
            )
            risk_out = await run_risk_critic(
                conn=conn,
                job_id=critic_args.job_id,
                candidate_skills=critic_args.candidate_skills,
                yoe=critic_args.yoe,
            )
            tool_trace.append({"tool": "risk_critic", "args": critic_args.model_dump(), "severity": risk_out.severity})

    candidate_ids = [int(item["job_id"]) for item in jobs]
    grounded_ids, rejected_ids = enforce_grounded_ids(candidate_ids, tool_returned_ids)
    filtered_jobs = [item for item in jobs if int(item["job_id"]) in set(grounded_ids)]

    reply = (
        f"Grounded {len(filtered_jobs)} matching roles from Postgres"
        + (f" (rejected {len(rejected_ids)} ungrounded IDs)." if rejected_ids else ".")
    )

    return AgentResponse(
        reply=reply,
        cited_job_ids=grounded_ids,
        tool_trace=tool_trace,
        risk_assessment=risk_out,
    )
