from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # plain string: demo accounts use reserved domains such as `.local` that strict validators reject
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    internal_ref: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=5000)


class CaseOut(BaseModel):
    id: str
    title: str
    internal_ref: str
    summary: str
    status: str
    is_synthetic: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class CaseOverview(CaseOut):
    files_count: int
    transactions_count: int
    entities_count: int
    relationships_count: int
    indicators_count: int
    unresolved_warnings: int
    findings_awaiting_review: int
    last_activity: datetime | None


class SourceFileOut(BaseModel):
    id: str
    original_name: str
    mime_type: str
    detected_kind: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime
    is_synthetic: bool
    status: str


class ParseRunOut(BaseModel):
    id: str
    source_file_id: str
    parser_name: str
    parser_version: str
    status: str
    column_mapping: dict
    warnings: list
    stats: dict
    started_at: datetime
    finished_at: datetime | None


class UploadResult(BaseModel):
    file: SourceFileOut
    parse_run: ParseRunOut | None
    preview: dict


class ColumnMappingRequest(BaseModel):
    mapping: dict[str, str]


class TransactionOut(BaseModel):
    id: str
    evidence_item_id: str
    external_reference: str | None
    account_ref: str
    counterparty_ref: str | None
    counterparty_name_raw: str | None
    datetime_raw: str | None
    datetime_utc: datetime | None
    time_precision: str
    direction: str
    amount_minor: int | None
    amount_raw: str | None
    currency: str
    narration_raw: str | None
    channel: str
    balance_after_minor: int | None
    quality_label: str
    warnings: list
    duplicate_of: str | None


class EvidenceItemOut(BaseModel):
    id: str
    source_file_id: str | None
    source_type: str
    source_locator: dict
    raw_value: str | None
    normalised_value: dict
    extraction_method: str
    parser_name: str
    parser_version: str
    event_time_start: datetime | None
    event_time_end: datetime | None
    time_precision: str
    source_timezone: str | None
    observed_at: datetime | None
    ingested_at: datetime
    quality_flags: list
    review_status: str


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    attributes: dict = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    evidence_level: str
    review_status: str
    valid_from: datetime | None
    valid_to: datetime | None
    observed_at: datetime | None
    heuristic_score: int | None
    limitations: list
    attributes: dict = {}


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    legend: dict[str, str]
    stats: dict


class EdgeDetail(BaseModel):
    edge: GraphEdge
    source_entity: GraphNode
    target_entity: GraphNode
    method: dict
    supporting_evidence: list[EvidenceItemOut]
    counter_evidence: list[dict]
    reviews: list[dict]


class ReviewRequest(BaseModel):
    decision: Literal["supported", "rejected", "needs_more_evidence"]
    reason: str = Field(default="", max_length=2000)


class TimelineEvent(BaseModel):
    id: str
    family: str  # transaction|complaint|url|dns|hosting|file
    time: datetime | None
    time_raw: str | None
    time_precision: str
    label: str
    evidence_item_id: str | None
    attributes: dict = {}


class SyntheticRequest(BaseModel):
    scenario_type: Literal[
        "phishing_to_mule",
        "fake_customer_care",
        "fake_loan_job",
        "investment_scam",
        "qr_marketplace",
        "multi_victim_network",
    ] = "phishing_to_mule"
    difficulty: Literal["clean", "messy", "high_noise", "adversarial"] = "messy"
    size: Literal["small", "medium", "large"] = "small"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    title: str | None = None


class SyntheticResult(BaseModel):
    case: CaseOut
    scenario_id: str
    public_manifest: dict
    files: list[UploadResult]


class ConnectorStatus(BaseModel):
    name: str
    status: Literal["configured", "not_configured", "unavailable", "mock", "live"]
    provider: str
    detail: str
    last_checked: datetime | None


class PathsResponse(BaseModel):
    paths: list[dict]
    features: dict[str, Any]
    reconciliation: list[dict]


TokenResponse.model_rebuild()
