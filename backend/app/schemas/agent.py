from typing import Optional, List
from pydantic import BaseModel, Field


class AgentCandidateSourceIn(BaseModel):
    """One OSINT candidate the agent's origin-investigator skill actually
    found (via web_search/web_fetch/browser/x_search). The backend only
    scores and ranks what it's given here -- it never invents a URL, date,
    author, or platform itself."""
    url: str
    title: Optional[str] = None
    platform: Optional[str] = None
    domain: Optional[str] = None
    publication_date: Optional[str] = Field(
        default="unknown",
        description='ISO date string as claimed by the source, or "unknown" if not determinable.',
    )
    accessible: bool = True
    inaccessible_reason: Optional[str] = Field(
        default=None,
        description="e.g. 'captcha', 'login_required', 'paywall', 'private_account' -- required when accessible=false.",
    )
    candidate_phash: Optional[str] = Field(
        default=None,
        description="Perceptual hash of the candidate media if the agent computed/obtained one; omit if unknown.",
    )


class AgentOriginSearchIn(BaseModel):
    candidates: List[AgentCandidateSourceIn] = Field(default_factory=list)
    queries_used: List[str] = Field(
        default_factory=list,
        description="The search queries the agent actually issued (for the event log / audit trail).",
    )
    is_demo: bool = Field(
        default=False,
        description="Set true only if these candidates are synthetic/placeholder data -- never mix real and fabricated sources.",
    )


class AgentEventIn(BaseModel):
    agent: str = Field(..., description="Which skill/agent is logging this, e.g. 'origin-investigator', 'social-tracer'.")
    action: str
    detail: Optional[str] = None
    stage: Optional[str] = Field(
        default=None,
        description="Optional. Must be one of the known investigation states if provided.",
    )


class AgentCompleteIn(BaseModel):
    status: str = Field(..., description="One of COMPLETED, PARTIAL, FAILED.")
    agent: str = Field(default="openclaw-agent")
    reason: Optional[str] = Field(
        default=None,
        description="Required (recommended) for PARTIAL/FAILED -- explain what could not be completed and why.",
    )


class AgentStageAck(BaseModel):
    investigation_id: str
    state: str
    message: str
