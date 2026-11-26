from typing import Literal
from pydantic import BaseModel, Field


class SearchJobsArgs(BaseModel):
    query: str = Field(..., min_length=1)
    location: str | None = None
    remote_only: bool = False
    role: str | None = None
    top_k: int = Field(5, ge=1, le=20)


class GetJobArgs(BaseModel):
    job_id: int = Field(..., ge=1)


class SavePrefArgs(BaseModel):
    skills: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    yoe: float | None = Field(default=None, ge=0.0, le=50.0)


class ExplainFitArgs(BaseModel):
    job_id: int = Field(..., ge=1)
    candidate_skills: list[str] = Field(default_factory=list)


class RiskCriticArgs(BaseModel):
    job_id: int = Field(..., ge=1)
    candidate_skills: list[str] = Field(default_factory=list)
    yoe: float | None = Field(default=None, ge=0.0, le=50.0)


class RiskCriticOutput(BaseModel):
    job_id: int
    gaps: list[str]
    severity: Literal["low", "medium", "high"]
    one_action_this_week: str


class AgentResponse(BaseModel):
    reply: str
    cited_job_ids: list[int]
    tool_trace: list[dict]
    risk_assessment: RiskCriticOutput | None = None
