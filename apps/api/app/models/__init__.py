"""Canonical relational model. PostgreSQL is the system of record; SQLite is used for local tests.

Design rules:
- Money is stored as integer minor units (paise). Never float.
- Every parsed value keeps raw_value + normalised_value + source_locator.
- Bitemporal: event/valid time, observed time, ingested time.
- Hidden synthetic ground truth is NOT in these tables (see app/synthetic/sealed_store.py).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, TypeDecorator,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo; PostgreSQL keeps it)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    analyst = "analyst"
    supervisor = "supervisor"
    admin = "admin"
    demo_analyst = "demo_analyst"  # one-click public visitor: synthetic workspace only, least privilege


class EvidenceLevel(str, enum.Enum):
    directly_observed = "directly_observed"
    corroborated = "corroborated"
    derived = "derived"
    candidate = "candidate"
    contradicted = "contradicted"
    stale = "stale"
    insufficient = "insufficient"


class ReviewStatus(str, enum.Enum):
    unreviewed = "unreviewed"
    supported = "supported"
    rejected = "rejected"
    needs_more_evidence = "needs_more_evidence"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.analyst)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # demo visitors: isolated workspace with an absolute expiry; cleaned up with their cases
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    internal_ref: Mapped[str] = mapped_column(String(100), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic_scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    memberships: Mapped[list["CaseMembership"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class CaseMembership(Base):
    __tablename__ = "case_memberships"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    role_in_case: Mapped[str] = mapped_column(String(20), default="analyst")
    case: Mapped[Case] = relationship(back_populates="memberships")


class SourceFile(Base):
    __tablename__ = "source_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    detected_kind: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded|parsing|parsed|needs_review|failed


class ParseRun(Base):
    __tablename__ = "parse_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_files.id", ondelete="CASCADE"), index=True)
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceItem(Base):
    """One extracted field/record with provenance."""
    __tablename__ = "evidence_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_files.id", ondelete="CASCADE"), nullable=True, index=True)
    parse_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("parse_runs.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40))  # bank_statement|complaint|technical_observation|connector|...
    source_locator: Mapped[dict] = mapped_column(JSON, default=dict)  # {page, row, column, sheet, cell, json_path, external_id}
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalised_value: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(60))
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(20))
    event_time_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    event_time_end: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(20), default="unknown")  # second|minute|day|month|unknown|ambiguous
    source_timezone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.unreviewed)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    evidence_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence_items.id", ondelete="CASCADE"))
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    account_ref: Mapped[str] = mapped_column(String(120), index=True)
    counterparty_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    counterparty_name_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    datetime_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    datetime_utc: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(20), default="unknown")
    direction: Mapped[str] = mapped_column(String(10), default="unknown")  # debit|credit|unknown
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    narration_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="unknown")
    balance_after_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_label: Mapped[str] = mapped_column(String(20), default="ok")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_of: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("case_id", "entity_type", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)  # account|person|vpa|phone|email|url|domain|ip|asn|dns_observation|evidence_file
    key: Mapped[str] = mapped_column(String(255), index=True)
    label: Mapped[str] = mapped_column(String(255))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Relationship(Base):
    __tablename__ = "relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    target_entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), index=True)
    direction: Mapped[str] = mapped_column(String(12), default="directed")
    evidence_level: Mapped[EvidenceLevel] = mapped_column(Enum(EvidenceLevel), default=EvidenceLevel.candidate)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    method_name: Mapped[str] = mapped_column(String(60))
    method_version: Mapped[str] = mapped_column(String(20))
    heuristic_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100 ranking score; NOT a probability
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.unreviewed)


class RelationshipEvidence(Base):
    __tablename__ = "relationship_evidence"
    __table_args__ = (UniqueConstraint("relationship_id", "evidence_item_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationships.id", ondelete="CASCADE"), index=True)
    evidence_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence_items.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="supports")


class CounterEvidence(Base):
    __tablename__ = "counter_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationships.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AnalystReview(Base):
    __tablename__ = "analyst_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationships.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    decision: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AuditEvent(Base):
    """Append-only."""
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SyntheticScenario(Base):
    """PUBLIC metadata only. Never store ground truth here."""
    __tablename__ = "synthetic_scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    scenario_type: Mapped[str] = mapped_column(String(40))
    difficulty: Mapped[str] = mapped_column(String(20))
    size: Mapped[str] = mapped_column(String(10))
    seed: Mapped[int] = mapped_column(Integer)
    scenario_version: Mapped[str] = mapped_column(String(20))
    generator_version: Mapped[str] = mapped_column(String(20))
    public_manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    sealed_truth_ref: Mapped[str] = mapped_column(String(120))  # opaque pointer into benchmark store
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(80))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


# ---------------------------------------------------------------------------------------------------------------------
# Victim claims / restitution readiness (complements the Money Restoration Module; never a legal or allocation decision)
# ---------------------------------------------------------------------------------------------------------------------

class ClaimStatus(str, enum.Enum):
    draft = "draft"
    investigator_checked = "investigator_checked"
    supervisor_checked = "supervisor_checked"
    export_ready = "export_ready"


class VictimClaim(Base):
    __tablename__ = "victim_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    victim_label: Mapped[str] = mapped_column(String(120))  # pseudonymous label, never a full identity
    complaint_ack_no: Mapped[str] = mapped_column(String(80), default="")
    fir_reference: Mapped[str] = mapped_column(String(80), default="")
    claimed_loss_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.draft)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class ClaimTransactionLink(Base):
    """A claim is traced through specific source transactions. The same transaction linked to two claims = competing claim."""
    __tablename__ = "claim_transaction_links"
    __table_args__ = (UniqueConstraint("claim_id", "transaction_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("victim_claims.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)  # portion of the transaction attributed to this claim (<= transaction amount)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class FundsRecord(Base):
    """Documented hold / restoration amounts. Requires a source evidence item; never inferred from a transaction."""
    __tablename__ = "funds_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # held | restored
    account_ref: Mapped[str] = mapped_column(String(120), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    source_evidence_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence_items.id"))
    source_kind: Mapped[str] = mapped_column(String(30))  # bank_notice | police_record | synthetic_simulated
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    reference: Mapped[str] = mapped_column(String(120), default="")
    recorded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CooperationPack(Base):
    """Manual handoff pack aligned to the cross-state cooperation request fields. Never submitted automatically."""
    __tablename__ = "cooperation_packs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    fir_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    endorsement_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | supervisor_endorsed | export_ready
    endorsed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    exported_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


# digital-twin increment tables (separate module to keep this file readable)
from app.models.twin import (AnalysisBranch, AnalysisRun, CandidateRule, EvidenceRequest, Hypothesis,  # noqa: E402,F401
                             IndependentReview, InvestigationEvent, PaymentInstruction, RoleReview)
