import re
import asyncpg
from app.agent.schemas import RiskCriticOutput

KNOWN_SKILLS = (
    "python", "java", "c++", "typescript", "javascript", "go", "rust",
    "sql", "postgresql", "postgres", "redis", "kafka", "docker", "kubernetes",
    "aws", "gcp", "azure", "fastapi", "react", "next.js", "pytorch", "llm", "rag",
)


def extract_required_skills(description: str) -> list[str]:
    text = (description or "").lower()
    found = [sk for sk in KNOWN_SKILLS if re.search(rf"\b{re.escape(sk)}\b", text)]
    return sorted(set(found))


async def run_risk_critic(
    conn: asyncpg.Connection,
    job_id: int,
    candidate_skills: list[str],
    yoe: float | None = None,
) -> RiskCriticOutput:
    job = await conn.fetchrow(
        "SELECT id, title, description FROM jobs WHERE id = $1",
        job_id,
    )
    if not job:
        return RiskCriticOutput(
            job_id=job_id,
            gaps=["Job record not found in index"],
            severity="high",
            one_action_this_week="Verify the target job posting ID before preparing an application.",
        )

    required = extract_required_skills(job["description"] or "")
    have = {s.strip().lower() for s in candidate_skills if s.strip()}
    missing = [req for req in required if req not in have]

    yoe_match = re.search(r"\b(\d+)\+\s*(?:years?|yrs?)\b", (job["description"] or "").lower())
    if yoe_match and yoe is not None:
        req_yoe = float(yoe_match.group(1))
        if yoe < req_yoe:
            missing.append(f"experience ({yoe:g} yrs vs {req_yoe:g}+ yrs required)")

    if len(missing) >= 3:
        severity = "high"
    elif len(missing) >= 1:
        severity = "medium"
    else:
        severity = "low"

    top_gap = missing[0] if missing else "core role requirements"
    action = (
        f"Build or document a small project/benchmark demonstrating {top_gap} and map it to {job['title']}."
        if missing
        else f"Tailor resume bullets with quantified impact aligned to {job['title']}."
    )

    return RiskCriticOutput(
        job_id=job_id,
        gaps=missing[:6],
        severity=severity,
        one_action_this_week=action,
    )
