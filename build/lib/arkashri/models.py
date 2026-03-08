from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arkashri.db import Base


class SignalType(str, enum.Enum):
    DETERMINISTIC = "DETERMINISTIC"
    ML = "ML"
    TREND = "TREND"


class ModelStatus(str, enum.Enum):
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class ExceptionStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ReportStatus(str, enum.Enum):
    GENERATED = "GENERATED"
    FAILED = "FAILED"


class AuditRunStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AuditStepStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UserRole(str, enum.Enum):
    ADMIN    = "ADMIN"     # Full access: create users, seal, verify, configure
    OPERATOR = "OPERATOR"  # Run audits, sign, generate opinions
    REVIEWER = "REVIEWER"  # Read + comment, pre-sign review
    READ_ONLY = "READ_ONLY"  # Dashboard + reports only


class User(Base):
    """
    Platform user — one row per person per tenant.
    Authenticated via POST /token (bcrypt password + JWT).
    """
    __tablename__ = "platform_user"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_tenant_user_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str]  = mapped_column(String(100), nullable=False)
    email: Mapped[str]      = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str]  = mapped_column(String(255), nullable=False)
    initials: Mapped[str]   = mapped_column(String(10),  nullable=False, default="?")
    role: Mapped[UserRole]  = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.REVIEWER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EngagementStatus(str, enum.Enum):
    PENDING  = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SEALED   = "SEALED"   # Engagement locked after multi-partner co-sign


class EngagementType(str, enum.Enum):
    # Core Financial
    FINANCIAL_AUDIT        = "financial_audit"
    INTERNAL_AUDIT         = "internal_audit"
    EXTERNAL_AUDIT         = "external_audit"
    STATUTORY_AUDIT        = "statutory_audit"
    # Regulatory & Risk
    COMPLIANCE_AUDIT       = "compliance_audit"
    OPERATIONAL_AUDIT      = "operational_audit"
    TAX_AUDIT              = "tax_audit"
    IT_AUDIT               = "it_audit"
    # Specialized
    FORENSIC_AUDIT         = "forensic_audit"
    PERFORMANCE_AUDIT      = "performance_audit"
    ENVIRONMENTAL_AUDIT    = "environmental_audit"
    PAYROLL_AUDIT          = "payroll_audit"
    QUALITY_AUDIT          = "quality_audit"
    SINGLE_AUDIT           = "single_audit"


class SealSessionStatus(str, enum.Enum):
    PENDING          = "PENDING"           # No signatures yet
    PARTIALLY_SIGNED = "PARTIALLY_SIGNED"  # At least 1, fewer than required
    FULLY_SIGNED     = "FULLY_SIGNED"      # All required signatures collected
    WITHDRAWN        = "WITHDRAWN"         # Session cancelled / reset


class PartnerRole(str, enum.Enum):
    ENGAGEMENT_PARTNER = "ENGAGEMENT_PARTNER"  # Primary signing partner
    EQCR_PARTNER       = "EQCR_PARTNER"        # Engagement Quality Control Reviewer
    COMPONENT_AUDITOR  = "COMPONENT_AUDITOR"   # Signs subsidiary / component opinion
    JOINT_AUDITOR      = "JOINT_AUDITOR"       # Joint audit (two firms)
    REGULATORY_COSIGN  = "REGULATORY_COSIGN"   # Regulator-mandated co-signature


class MaterialityBasis(str, enum.Enum):
    REVENUE = "REVENUE"
    PROFIT_BEFORE_TAX = "PROFIT_BEFORE_TAX"
    TOTAL_ASSETS = "TOTAL_ASSETS"
    NET_ASSETS = "NET_ASSETS"
    GROSS_MARGIN = "GROSS_MARGIN"


class AuditOpinionType(str, enum.Enum):
    UNMODIFIED = "UNMODIFIED"
    QUALIFIED = "QUALIFIED"
    ADVERSE = "ADVERSE"
    DISCLAIMER = "DISCLAIMER"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class ApprovalActionType(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    COMMENTED = "COMMENTED"


class FrameworkType(str, enum.Enum):
    IFRS = "IFRS"
    US_GAAP = "US_GAAP"
    IND_AS = "IND_AS"
    LOCAL_GAAP = "LOCAL_GAAP"
    PCAOB = "PCAOB"
    ISA = "ISA"
    OTHER = "OTHER"


class PolicyEnforcementAction(str, enum.Enum):
    WARN = "WARN"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    LOG_ONLY = "LOG_ONLY"


class KnowledgeSourceType(str, enum.Enum):
    LAW = "LAW"
    STANDARD = "STANDARD"
    POLICY = "POLICY"
    INTERNAL_NOTE = "INTERNAL_NOTE"


class ClientRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    READ_ONLY = "READ_ONLY"


class CrisisTriggerType(str, enum.Enum):
    REGULATORY_NOTICE = "REGULATORY_NOTICE"
    FRAUD_DETECTED = "FRAUD_DETECTED"
    LITIGATION_HOLD = "LITIGATION_HOLD"
    SYSTEM_COMPROMISE = "SYSTEM_COMPROMISE"
    WHISTLEBLOWER = "WHISTLEBLOWER"


class CrisisStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    ARCHIVED = "ARCHIVED"


class ContinuousAuditAction(str, enum.Enum):
    ALERT_ONLY = "ALERT_ONLY"
    INCREASE_SAMPLE = "INCREASE_SAMPLE"
    TRIGGER_CRISIS = "TRIGGER_CRISIS"
    BLOCK_TRANSACTION = "BLOCK_TRANSACTION"


class InvestigationType(str, enum.Enum):
    RELATED_PARTY = "RELATED_PARTY"
    ASSET_MISAPPROPRIATION = "ASSET_MISAPPROPRIATION"
    FINANCIAL_STATEMENT_FRAUD = "FINANCIAL_STATEMENT_FRAUD"
    CORRUPTION = "CORRUPTION"


class ESGCategory(str, enum.Enum):
    ENVIRONMENTAL = "ENVIRONMENTAL"
    SOCIAL = "SOCIAL"
    GOVERNANCE = "GOVERNANCE"


class ArchiveStatus(str, enum.Enum):
    SEALED = "SEALED"
    PENDING = "PENDING"
    COMPROMISED = "COMPROMISED"


class RegulatorySourceType(str, enum.Enum):
    API_JSON = "API_JSON"
    RSS = "RSS"
    HTML = "HTML"
    MANUAL = "MANUAL"


class IngestRunStatus(str, enum.Enum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ScheduleCadence(str, enum.Enum):
    HOURLY = "HOURLY"
    DAILY = "DAILY"


class ScheduleState(str, enum.Enum):
    IDLE = "IDLE"
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    FAILED = "FAILED"


class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(str, enum.Enum):
    SYNC_FAILURE = "SYNC_FAILURE"
    SYNC_RECOVERY = "SYNC_RECOVERY"


class RuleRegistry(Base):
    __tablename__ = "rule_registry"
    __table_args__ = (UniqueConstraint("rule_key", "version", name="uq_rule_key_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    expression: Mapped[dict] = mapped_column(JSON, nullable=False)
    signal_value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    severity_floor: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FormulaRegistry(Base):
    __tablename__ = "formula_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    formula_text: Mapped[str] = mapped_column(Text, nullable=False)
    formula_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    component_caps: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeightSet(Base):
    __tablename__ = "weight_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    weight_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list[WeightEntry]] = relationship(back_populates="weight_set", cascade="all, delete-orphan")


class WeightEntry(Base):
    __tablename__ = "weight_entry"
    __table_args__ = (
        UniqueConstraint("weight_set_id", "signal_type", "signal_key", name="uq_weight_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weight_set_id: Mapped[int] = mapped_column(ForeignKey("weight_set.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType, name="signal_type"), nullable=False)
    signal_key: Mapped[str] = mapped_column(String(128), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    weight_set: Mapped[WeightSet] = relationship(back_populates="entries")


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (UniqueConstraint("model_key", "version", name="uq_model_key_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hyperparams_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fairness_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ModelStatus] = mapped_column(Enum(ModelStatus, name="model_status"), nullable=False)
    lower_bound: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    upper_bound: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    __tablename__ = "financial_transaction"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    decision: Mapped[Decision | None] = relationship(back_populates="transaction", uselist=False)


class Decision(Base):
    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("financial_transaction.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    final_risk: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_set_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rule_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped[Transaction] = relationship(back_populates="decision")
    exception_case: Mapped[ExceptionCase | None] = relationship(
        back_populates="decision", uselist=False, cascade="all, delete-orphan"
    )

class DecisionOverride(Base):
    __tablename__ = "decision_override"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision.id", ondelete="CASCADE"), nullable=False
    )
    original_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    original_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    overridden_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    overridden_by_user: Mapped[str] = mapped_column(String(120), nullable=False)
    override_reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    decision: Mapped[Decision] = relationship("Decision", backref="overrides")


class ESGMetrics(Base):
    __tablename__ = "esg_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    carbon_footprint_scope_1: Mapped[float | None] = mapped_column(Float)
    carbon_footprint_scope_2: Mapped[float | None] = mapped_column(Float)
    carbon_footprint_scope_3: Mapped[float | None] = mapped_column(Float)
    board_diversity_pct: Mapped[float | None] = mapped_column(Float)
    supply_chain_transparency_index: Mapped[float | None] = mapped_column(Float)
    active_regulatory_fines: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    engagement: Mapped[Engagement] = relationship("Engagement", backref="esg_metrics")


class ForensicProfile(Base):
    __tablename__ = "forensic_profile"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    transaction_velocity_score: Mapped[float | None] = mapped_column(Float)
    benfords_law_deviation: Mapped[float | None] = mapped_column(Float)
    offshore_routing_instances: Mapped[int | None] = mapped_column(Integer)
    ubo_opacity_index: Mapped[float | None] = mapped_column(Float)
    sanctions_hit_probability: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    engagement: Mapped[Engagement] = relationship("Engagement", backref="forensic_profile")


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    signature_key_id: Mapped[str | None] = mapped_column(String(128))
    signature: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExceptionCase(Base):
    __tablename__ = "exception_case"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, name="exception_status"), nullable=False, default=ExceptionStatus.OPEN
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    decision: Mapped[Decision] = relationship(back_populates="exception_case")


class ReportJob(Base):
    __tablename__ = "report_job"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.GENERATED
    )
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChainAnchor(Base):
    __tablename__ = "chain_anchor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    window_start_event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    window_end_event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    anchor_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attestations: Mapped[list[ChainAttestation]] = relationship(
        back_populates="chain_anchor",
        cascade="all, delete-orphan",
    )


class AgentProfile(Base):
    __tablename__ = "agent_profile"
    __table_args__ = (UniqueConstraint("agent_key", name="uq_agent_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditRun(Base):
    __tablename__ = "audit_run"
    __table_args__ = (UniqueConstraint("run_hash", name="uq_audit_run_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    audit_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[AuditRunStatus] = mapped_column(
        Enum(AuditRunStatus, name="audit_run_status"), nullable=False, default=AuditRunStatus.DRAFT
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    run_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    steps: Mapped[list[AuditRunStep]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AuditRunStep(Base):
    __tablename__ = "audit_run_step"
    __table_args__ = (
        UniqueConstraint("run_id", "phase_id", "step_id", name="uq_audit_run_step_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_run.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_key: Mapped[str | None] = mapped_column(String(100))
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[AuditStepStatus] = mapped_column(
        Enum(AuditStepStatus, name="audit_step_status"), nullable=False, default=AuditStepStatus.PENDING
    )
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[AuditRun] = relationship(back_populates="steps")
    approval_requests: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="step",
        cascade="all, delete-orphan",
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_request"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), nullable=False, default=ApprovalStatus.PENDING
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_notes: Mapped[str | None] = mapped_column(Text)
    step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("audit_run_step.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    step: Mapped[AuditRunStep | None] = relationship(back_populates="approval_requests")
    actions: Mapped[list[ApprovalAction]] = relationship(back_populates="request", cascade="all, delete-orphan")


class ApprovalAction(Base):
    __tablename__ = "approval_action"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_request.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[ApprovalActionType] = mapped_column(
        Enum(ApprovalActionType, name="approval_action_type"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    action_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    request: Mapped[ApprovalRequest] = relationship(back_populates="actions")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_document"
    __table_args__ = (
        UniqueConstraint("document_key", "jurisdiction", "version", name="uq_knowledge_document_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        Enum(KnowledgeSourceType, name="knowledge_source_type"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class RagQueryLog(Base):
    __tablename__ = "rag_query_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    audit_type: Mapped[str | None] = mapped_column(String(64))
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChainAttestation(Base):
    __tablename__ = "chain_attestation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_anchor_id: Mapped[int] = mapped_column(
        ForeignKey("chain_anchor.id", ondelete="CASCADE"), nullable=False
    )
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    network: Mapped[str] = mapped_column(String(100), nullable=False)
    tx_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    attestation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chain_anchor: Mapped[ChainAnchor] = relationship(back_populates="attestations")


class ApiClient(Base):
    __tablename__ = "api_client"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_client_key_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[ClientRole] = mapped_column(
        Enum(ClientRole, name="client_role"), nullable=False, default=ClientRole.READ_ONLY
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint("tenant_id", "jurisdiction", "idempotency_key", name="uq_idempotency_scope_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegulatorySource(Base):
    __tablename__ = "regulatory_source"
    __table_args__ = (UniqueConstraint("source_key", name="uq_regulatory_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    authority: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[RegulatorySourceType] = mapped_column(
        Enum(RegulatorySourceType, name="regulatory_source_type"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    parser_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingest_runs: Mapped[list[RegulatoryIngestRun]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    schedules: Mapped[list[RegulatorySyncSchedule]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[RegulatorySyncAlert]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[RegulatoryDocument]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class RegulatoryIngestRun(Base):
    __tablename__ = "regulatory_ingest_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[IngestRunStatus] = mapped_column(
        Enum(IngestRunStatus, name="ingest_run_status"), nullable=False, default=IngestRunStatus.STARTED
    )
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[RegulatorySource] = relationship(back_populates="ingest_runs")
    alerts: Mapped[list[RegulatorySyncAlert]] = relationship(back_populates="ingest_run")


class RegulatorySyncSchedule(Base):
    __tablename__ = "regulatory_sync_schedule"
    __table_args__ = (UniqueConstraint("source_id", name="uq_regulatory_schedule_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source.id", ondelete="CASCADE"), nullable=False
    )
    cadence: Mapped[ScheduleCadence] = mapped_column(
        Enum(ScheduleCadence, name="schedule_cadence"), nullable=False
    )
    interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    daily_hour: Mapped[int | None] = mapped_column(Integer)
    daily_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    backoff_base_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[ScheduleState] = mapped_column(
        Enum(ScheduleState, name="schedule_state"), nullable=False, default=ScheduleState.IDLE
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[RegulatorySource] = relationship(back_populates="schedules")
    alerts: Mapped[list[RegulatorySyncAlert]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
    )


class RegulatorySyncAlert(Base):
    __tablename__ = "regulatory_sync_alert"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("regulatory_sync_schedule.id"))
    ingest_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regulatory_ingest_run.id"))
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity"), nullable=False
    )
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[RegulatorySource] = relationship(back_populates="alerts")
    schedule: Mapped[RegulatorySyncSchedule | None] = relationship(back_populates="alerts")
    ingest_run: Mapped[RegulatoryIngestRun | None] = relationship(back_populates="alerts")


class RegulatoryDocument(Base):
    __tablename__ = "regulatory_document"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_regulatory_document_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source.id", ondelete="CASCADE"), nullable=False
    )
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    authority: Mapped[str] = mapped_column(String(120), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    document_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promoted_knowledge_doc_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_document.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[RegulatorySource] = relationship(back_populates="documents")
    promoted_knowledge_doc: Mapped[KnowledgeDocument | None] = relationship()


class Engagement(Base):
    __tablename__ = "engagement"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    engagement_type: Mapped[EngagementType] = mapped_column(
        Enum(EngagementType, name="engagement_type"), nullable=False, default=EngagementType.STATUTORY_AUDIT
    )
    status: Mapped[EngagementStatus] = mapped_column(
        Enum(EngagementStatus, name="engagement_status"), nullable=False, default=EngagementStatus.PENDING
    )
    independence_cleared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kyc_cleared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_check_notes: Mapped[str | None] = mapped_column(Text)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seal_hash: Mapped[str | None] = mapped_column(String(64))
    # ── Seal persistence & key provenance (PCAOB hardening) ────────────────────
    seal_bundle: Mapped[dict | None] = mapped_column(JSON)           # Full WORM bundle payload — enables replay verification
    seal_key_version: Mapped[str | None] = mapped_column(String(32)) # HMAC key version used (supports key rotation audit)
    seal_verify_status: Mapped[str | None] = mapped_column(String(16)) # VERIFIED | MISMATCH | PENDING
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )



class MaterialityAssessment(Base):
    __tablename__ = "materiality_assessment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    basis: Mapped[MaterialityBasis] = mapped_column(
        Enum(MaterialityBasis, name="materiality_basis"), nullable=False
    )
    basis_amount: Mapped[float] = mapped_column(Float, nullable=False)
    overall_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    overall_materiality: Mapped[float] = mapped_column(Float, nullable=False)
    performance_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    performance_materiality: Mapped[float] = mapped_column(Float, nullable=False)
    trivial_threshold_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    trivial_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    engagement: Mapped[Engagement] = relationship()


class AuditOpinion(Base):
    __tablename__ = "audit_opinion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    opinion_type: Mapped[AuditOpinionType] = mapped_column(
        Enum(AuditOpinionType, name="audit_opinion_type"), nullable=False
    )
    basis_for_opinion: Mapped[str] = mapped_column(Text, nullable=False)
    key_audit_matters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signed_by: Mapped[str | None] = mapped_column(String(100))
    signature_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Context-lock fields (PCAOB / NFRA defensibility) ──────────────────────
    # Frozen at opinion generation — never updated after creation
    opinion_hash: Mapped[str | None] = mapped_column(String(64))          # SHA-256 of canonical opinion JSON
    weight_set_version: Mapped[int | None] = mapped_column(Integer)        # WeightSet version used
    rule_snapshot_hash: Mapped[str | None] = mapped_column(String(64))     # Hash of active RuleRegistry state
    decision_hashes: Mapped[list] = mapped_column(JSON, default=list)      # output_hash of every Decision in scope
    exception_ids: Mapped[list] = mapped_column(JSON, default=list)        # UUID list of ExceptionCases evaluated
    materiality_amount: Mapped[float | None] = mapped_column(Float)        # Materiality threshold applied
    system_version: Mapped[str | None] = mapped_column(String(32))         # Arkashri version tag at generation

    engagement: Mapped[Engagement] = relationship()


# ─── Multi-Partner Co-Sign Tables ─────────────────────────────────────────────

class SealSession(Base):
    """
    Represents a pending multi-partner sign-off session for one engagement.
    Sealing is impossible until status == FULLY_SIGNED.
    """
    __tablename__ = "seal_session"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False
    )
    required_signatures: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    current_signature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[SealSessionStatus] = mapped_column(
        Enum(SealSessionStatus, name="seal_session_status"), nullable=False,
        default=SealSessionStatus.PENDING,
    )
    # Frozen snapshot of the opinion + context at time of first signature
    opinion_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    engagement: Mapped[Engagement] = relationship()
    signatures: Mapped[list[SealSignature]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SealSignature(Base):
    """
    One partner's signature within a SealSession.
    Withdrawal resets the session to PENDING (creates an audit trail entry).
    """
    __tablename__ = "seal_signature"
    __table_args__ = (
        UniqueConstraint("seal_session_id", "partner_user_id", name="uq_session_partner"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seal_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("seal_session.id", ondelete="CASCADE"), nullable=False
    )
    partner_user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    partner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[PartnerRole] = mapped_column(
        Enum(PartnerRole, name="partner_role"), nullable=False,
        default=PartnerRole.ENGAGEMENT_PARTNER,
    )
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False, default="IN")
    override_count_acknowledged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    override_ack_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 proof
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawal_reason: Mapped[str | None] = mapped_column(Text)

    session: Mapped[SealSession] = relationship(back_populates="signatures")


class RegulatoryFramework(Base):
    __tablename__ = "regulatory_framework"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    framework_type: Mapped[FrameworkType] = mapped_column(
        Enum(FrameworkType, name="framework_type"), nullable=False, default=FrameworkType.IFRS
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrossBorderPolicy(Base):
    __tablename__ = "cross_border_policy"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    target_jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_name: Mapped[str] = mapped_column(String(255), nullable=False)
    enforcement_action: Mapped[PolicyEnforcementAction] = mapped_column(
        Enum(PolicyEnforcementAction, name="policy_enforcement_action"), nullable=False, default=PolicyEnforcementAction.WARN
    )
    constraint_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditPlaybook(Base):
    __tablename__ = "audit_playbook"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_type: Mapped[EngagementType] = mapped_column(
        Enum(EngagementType, name="engagement_type"), nullable=False
    )
    sector: Mapped[str | None] = mapped_column(String(100))
    playbook_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    workflow_template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    required_phases: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SectorControl(Base):
    __tablename__ = "sector_control"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    control_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    control_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    risk_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    test_procedures: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_txn_tenant_jurisdiction_created", Transaction.tenant_id, Transaction.jurisdiction, Transaction.created_at)
Index("ix_audit_stream", AuditEvent.tenant_id, AuditEvent.jurisdiction, AuditEvent.id)
Index("ix_exception_case_tenant_jurisdiction_status", ExceptionCase.tenant_id, ExceptionCase.jurisdiction, ExceptionCase.status)
Index("ix_report_job_tenant_jurisdiction_created", ReportJob.tenant_id, ReportJob.jurisdiction, ReportJob.created_at)
Index("ix_engagement_tenant_jurisdiction_status", Engagement.tenant_id, Engagement.jurisdiction, Engagement.status)
Index("ix_chain_anchor_tenant_jurisdiction_id", ChainAnchor.tenant_id, ChainAnchor.jurisdiction, ChainAnchor.id)
Index("ix_audit_run_tenant_jurisdiction_created", AuditRun.tenant_id, AuditRun.jurisdiction, AuditRun.created_at)
Index("ix_audit_run_step_run_sequence", AuditRunStep.run_id, AuditRunStep.sequence_no)
Index(
    "ix_approval_request_tenant_jurisdiction_status",
    ApprovalRequest.tenant_id,
    ApprovalRequest.jurisdiction,
    ApprovalRequest.status,
)

class CrisisEvent(Base):
    __tablename__ = "crisis_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_type: Mapped[CrisisTriggerType] = mapped_column(Enum(CrisisTriggerType, name="crisis_trigger_type"), nullable=False)
    status: Mapped[CrisisStatus] = mapped_column(Enum(CrisisStatus, name="crisis_status"), nullable=False, default=CrisisStatus.ACTIVE)
    freeze_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    escalated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ContinuousAuditRule(Base):
    __tablename__ = "continuous_audit_rule"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    action_on_breach: Mapped[ContinuousAuditAction] = mapped_column(Enum(ContinuousAuditAction, name="continuous_audit_action"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ForensicInvestigation(Base):
    __tablename__ = "forensic_investigation"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(255), nullable=False)
    investigation_type: Mapped[InvestigationType] = mapped_column(Enum(InvestigationType, name="investigation_type"), nullable=False)
    findings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ESGMetric(Base):
    __tablename__ = "esg_metric"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    metric_category: Mapped[ESGCategory] = mapped_column(Enum(ESGCategory, name="esg_category"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_source: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AIGovernanceLog(Base):
    __tablename__ = "ai_governance_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    human_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SovereignArchive(Base):
    __tablename__ = "sovereign_archive"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(20), nullable=False)
    archive_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ArchiveStatus] = mapped_column(Enum(ArchiveStatus, name="archive_status"), nullable=False, default=ArchiveStatus.PENDING)
    archive_location: Mapped[str] = mapped_column(String(500), nullable=False)
    retention_period_years: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

Index(
    "ix_knowledge_document_jurisdiction_source",
    KnowledgeDocument.jurisdiction,
    KnowledgeDocument.source_type,
    KnowledgeDocument.created_at,
)
Index("ix_knowledge_chunk_document_chunk", KnowledgeChunk.document_id, KnowledgeChunk.chunk_index)
Index("ix_rag_query_log_tenant_jurisdiction_created", RagQueryLog.tenant_id, RagQueryLog.jurisdiction, RagQueryLog.created_at)
Index("ix_chain_attestation_anchor_id", ChainAttestation.chain_anchor_id, ChainAttestation.id)
Index("ix_api_client_role_active", ApiClient.role, ApiClient.is_active)
Index(
    "ix_idempotency_scope_created",
    IdempotencyRecord.tenant_id,
    IdempotencyRecord.jurisdiction,
    IdempotencyRecord.created_at,
)
Index(
    "ix_regulatory_source_scope_active",
    RegulatorySource.jurisdiction,
    RegulatorySource.authority,
    RegulatorySource.is_active,
)
Index(
    "ix_regulatory_ingest_run_source_started",
    RegulatoryIngestRun.source_id,
    RegulatoryIngestRun.started_at,
)
Index(
    "ix_regulatory_document_scope_published",
    RegulatoryDocument.jurisdiction,
    RegulatoryDocument.authority,
    RegulatoryDocument.published_on,
)
Index(
    "ix_regulatory_schedule_next_run",
    RegulatorySyncSchedule.is_active,
    RegulatorySyncSchedule.next_run_at,
)
Index(
    "ix_regulatory_alert_scope_created",
    RegulatorySyncAlert.source_id,
    RegulatorySyncAlert.created_at,
)
Index(
    "ix_regulatory_alert_ack",
    RegulatorySyncAlert.is_acknowledged,
    RegulatorySyncAlert.created_at,
)

# ─── ERP Integration Models ───────────────────────────────────────────────────

class ERPSystem(str, enum.Enum):
    SAP_S4HANA    = "SAP_S4HANA"
    ORACLE_FUSION = "ORACLE_FUSION"
    TALLY_PRIME   = "TALLY_PRIME"
    ZOHO_BOOKS    = "ZOHO_BOOKS"
    QUICKBOOKS    = "QUICKBOOKS"
    GENERIC_CSV   = "GENERIC_CSV"


class ERPSyncStatus(str, enum.Enum):
    IDLE      = "IDLE"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    PARTIAL   = "PARTIAL"    # Some records failed
    FAILED    = "FAILED"


class ERPConnection(Base):
    """
    Tenant-level ERP connection configuration.
    Stores which ERP system is connected and the last sync state.
    Credentials are stored encrypted in connection_config.
    """
    __tablename__ = "erp_connection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "erp_system", name="uq_tenant_erp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str]  = mapped_column(String(100), nullable=False)
    erp_system: Mapped[ERPSystem] = mapped_column(
        Enum(ERPSystem, name="erp_system"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool]   = mapped_column(Boolean, nullable=False, default=True)
    # Encrypted credentials + endpoint config (AES-256 in production)
    connection_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Sync state
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[ERPSyncStatus] = mapped_column(
        Enum(ERPSyncStatus, name="erp_sync_status"), nullable=False, default=ERPSyncStatus.IDLE
    )
    sync_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_records_ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sync_logs: Mapped[list[ERPSyncLog]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class ERPSyncLog(Base):
    """
    One row per ERP sync run.
    Full audit trail: what was synced, how many records, what failed.
    """
    __tablename__ = "erp_sync_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("erp_connection.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    erp_system: Mapped[ERPSystem] = mapped_column(
        Enum(ERPSystem, name="erp_system"), nullable=False
    )
    status: Mapped[ERPSyncStatus] = mapped_column(
        Enum(ERPSyncStatus, name="erp_sync_status"), nullable=False, default=ERPSyncStatus.RUNNING
    )
    records_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_ingested: Mapped[int]  = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int]    = mapped_column(Integer, nullable=False, default=0)
    records_flagged: Mapped[int]   = mapped_column(Integer, nullable=False, default=0)  # risk_flags present
    sync_duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)
    date_range_from: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    date_range_to: Mapped[str | None]   = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connection: Mapped[ERPConnection] = relationship(back_populates="sync_logs")


Index("ix_erp_connection_tenant", ERPConnection.tenant_id, ERPConnection.erp_system)
Index("ix_erp_sync_log_connection", ERPSyncLog.connection_id, ERPSyncLog.started_at)
