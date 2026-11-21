"""Digital-twin increment (2026-11): events, payment instructions, hypotheses/reviews, evidence requests, role review,
analysis branches/runs, candidate rules. Every row keeps provenance; nothing here stores sealed ground truth."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models import UTCDateTime, new_id, utcnow


class InvestigationEvent(Base):
    """Typed event of the fraud-operation digital twin that is NOT derivable from an evidence item (e.g. a victim-reported
    contact entered by an analyst). Derived events are assembled at query time from evidence/transactions/observations."""
    __tablename__ = "investigation_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    layer: Mapped[str] = mapped_column(String(24), default="victim_journey")  # victim_journey|artefact|payment|financial|infrastructure|investigation
    evidence_class: Mapped[str] = mapped_column(String(24), default="reported")  # reported|directly_observed|extracted|corroborated|derived|candidate|contradicted|unresolved
    event_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(20), default="unknown")
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reported_by: Mapped[str] = mapped_column(String(120), default="")  # e.g. "victim (complaint)", "analyst"
    reported_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source_evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), nullable=True)
    source_file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_files.id"), nullable=True)
    source_locator: Mapped[dict] = mapped_column(JSON, default=dict)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class PaymentInstruction(Base):
    """A decoded payment instruction (QR payload, upi:// URI, pasted text). Raw payload is always kept."""
    __tablename__ = "payment_instructions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_files.id"), nullable=True)
    source_evidence_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), nullable=True)
    source_locator: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_type: Mapped[str] = mapped_column(String(24))  # upi|url|text|unsupported|invalid
    raw_payload: Mapped[str] = mapped_column(Text)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # parsed raw params incl. unknown ones
    payee_vpa: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payee_name_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(40))  # qr_decoder|uri_text|ocr_text|manual
    decoder_version: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100 decoder/OCR confidence where available
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Hypothesis(Base):
    """An analyst hypothesis under test (relationship, path, role, campaign, other). Versioned by appending; never rewritten silently."""
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="other")
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text, default="")
    subject_refs: Mapped[dict] = mapped_column(JSON, default=dict)  # {relationship_ids:[], account_refs:[], case_ids:[], path_index:int}
    supporting_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    alternatives: Mapped[list] = mapped_column(JSON, default=list)  # alternative explanations (text)
    status: Mapped[str] = mapped_column(String(24), default="open")  # open|under_review|supported|disputed|unresolved|withdrawn
    version: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{version, statement, status, changed_by, changed_at, reason}]
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class IndependentReview(Base):
    """Independent reviewer assessment of a hypothesis. Append-only; dissent is preserved."""
    __tablename__ = "independent_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str] = mapped_column(String(36), ForeignKey("hypotheses.id", ondelete="CASCADE"), index=True)
    hypothesis_version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(10), default="open")  # blind|open
    decision: Mapped[str] = mapped_column(String(24))  # agree|disagree|request_evidence|unresolved
    rationale: Mapped[str] = mapped_column(Text)
    evidence_reviewed: Mapped[list] = mapped_column(JSON, default=list)
    requested_evidence: Mapped[list] = mapped_column(JSON, default=list)
    is_dissent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class EvidenceRequest(Base):
    """Preservation / information request draft. Status 'dispatch_recorded' is set only by a human recording an actual dispatch;
    the system never sends anything. Retention deadlines appear only with a verified source."""
    __tablename__ = "evidence_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    organisation_type: Mapped[str] = mapped_column(String(40), default="bank")  # bank|payment_app|telecom|hosting|registrar|isp|platform|police|other
    target_record: Mapped[str] = mapped_column(String(200), default="")
    target_entity: Mapped[str] = mapped_column(String(200), default="")
    window_from: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    window_to: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    required_fields: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    could_resolve: Mapped[list] = mapped_column(JSON, default=list)
    would_not_establish: Mapped[list] = mapped_column(JSON, default=list)
    ranking: Mapped[dict] = mapped_column(JSON, default=dict)  # IVOI component breakdown at suggestion time
    retention: Mapped[dict] = mapped_column(JSON, default=dict)  # {verified: bool, source_url, effective_date, period_days, note}
    legal_authority: Mapped[str] = mapped_column(String(200), default="")
    requesting_officer: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="suggested")
    status_history: Mapped[list] = mapped_column(JSON, default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class RoleReview(Base):
    """Role-sensitive account/human-context review. Propositions are kept apart; none is a legal finding."""
    __tablename__ = "role_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    account_ref: Mapped[str] = mapped_column(String(120), index=True)
    propositions: Mapped[dict] = mapped_column(JSON, default=dict)  # {key: {status, supports:[ev ids], contradicts:[ev ids], notes}}
    status: Mapped[str] = mapped_column(String(24), default="UNASSESSED")  # UNASSESSED|REVIEW_REQUIRED|CONFLICTING_EVIDENCE|INDETERMINATE|HUMAN_REVIEWED
    open_questions: Mapped[list] = mapped_column(JSON, default=list)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_rationale: Mapped[str] = mapped_column(Text, default="")
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class AnalysisBranch(Base):
    """Alternative analytical interpretation ('git for investigations'). Copies analysis assumptions only; never source evidence."""
    __tablename__ = "analysis_branches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    hypothesis_statement: Mapped[str] = mapped_column(Text, default="")
    base_snapshot_hash: Mapped[str] = mapped_column(String(64))  # hash of source files + evidence ids at branch time
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AnalysisRun(Base):
    """Persisted deterministic analysis output (counterfactual, bounded flow, campaign comparison, branch comparison...)."""
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(20))
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CandidateRule(Base):
    """Prevention-rule compiler output: a versioned candidate rule evaluated on held-out synthetic data. Never deployed."""
    __tablename__ = "candidate_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    typology: Mapped[str] = mapped_column(String(60))
    conditions: Mapped[list] = mapped_column(JSON, default=list)  # [{feature, op, value}]
    source_hypothesis_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|rejected|expired
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_due: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
