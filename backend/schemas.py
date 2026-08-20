import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Category = Literal["SECURITY", "LOGIC", "MEMORY", "QUALITY"]
NodeStatus = Literal["PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED"]
RunStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED_VALIDATION", "ERROR"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class ToolViolation(BaseModel):
    """Deterministic rule violation emitted by an MCP linter tool."""

    model_config = ConfigDict(extra="ignore")

    tool: str
    rule_id: str
    file_path: str
    line: int
    severity: Severity = "MEDIUM"
    confidence: str = "MEDIUM"
    message: str
    cwe: Optional[str] = None
    snippet: Optional[str] = None
    in_diff: bool = True


class PolicyChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_uid)
    title: str
    category: str = "OWASP"
    cwe: List[str] = Field(default_factory=list)
    content: str
    source: str = "builtin"
    embedding: List[float] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)


class PolicyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(default="CUSTOM", max_length=60)
    cwe: List[str] = Field(default_factory=list)
    content: str = Field(min_length=10, max_length=8000)


class RetrievedPolicy(BaseModel):
    id: str
    title: str
    category: str
    cwe: List[str] = Field(default_factory=list)
    content: str
    score: float
    backend: str = "mongo"


# ---------- Structured LLM output (Pydantic v2 contract) ----------


class PatchComment(BaseModel):
    """One inline GitHub review comment. Schema is enforced on the LLM."""

    model_config = ConfigDict(extra="ignore")

    file_path: str = Field(min_length=1, max_length=400)
    line: int = Field(gt=0)
    severity: Severity
    category: Category
    title: str = Field(min_length=3, max_length=140)
    rationale: str = Field(min_length=10, max_length=2000)
    cwe: Optional[str] = Field(default=None, max_length=40)
    owasp: Optional[str] = Field(default=None, max_length=80)
    rule_id: Optional[str] = Field(default=None, max_length=80)
    suggested_code: Optional[str] = Field(default=None, max_length=4000)
    policy_citation: Optional[str] = Field(default=None, max_length=400)


class ReviewDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=10, max_length=3000)
    risk_score: int = Field(ge=0, le=100)
    comments: List[PatchComment] = Field(default_factory=list)


# ---------- Run persistence ----------


class TraceNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node: str
    label: str
    status: NodeStatus = "PENDING"
    attempt: int = 1
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: int = 0
    detail: str = ""
    error: Optional[str] = None


class RunMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    llm_calls: int = 0
    llm_retries: int = 0
    validation_attempts: int = 0
    tool_violations: int = 0
    policies_retrieved: int = 0


class ChangedFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    language: str
    added_lines: List[int] = Field(default_factory=list)
    patch: str = ""
    content: str = ""
    skipped_reason: Optional[str] = None


class ReviewRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_uid)
    source: Literal["webhook", "manual", "simulation"] = "simulation"
    repo_full_name: str
    pr_number: int = 0
    pr_title: str = ""
    author: str = ""
    head_sha: str = ""
    html_url: str = ""
    status: RunStatus = "QUEUED"
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    latency_ms: int = 0
    summary: str = ""
    risk_score: int = 0
    trace: List[TraceNode] = Field(default_factory=list)
    findings: List[PatchComment] = Field(default_factory=list)
    tool_violations: List[ToolViolation] = Field(default_factory=list)
    retrieved_policies: List[RetrievedPolicy] = Field(default_factory=list)
    changed_files: List[ChangedFile] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    validation_errors: List[str] = Field(default_factory=list)
    github_review_url: Optional[str] = None
    published: bool = False
    error: Optional[str] = None


# ---------- API request bodies ----------


class SimulateRequest(BaseModel):
    repo_full_name: str = Field(default="local/sandbox", max_length=140)
    pr_number: int = Field(default=0, ge=0)
    pr_title: str = Field(default="Simulated pull request", max_length=200)
    author: str = Field(default="local-dev", max_length=100)
    file_path: str = Field(default="app/main.py", max_length=300)
    content: str = Field(min_length=1, max_length=60000)


class GithubReviewRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=140)
    pull_number: int = Field(gt=0)
    publish: bool = False


class PolicySearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
