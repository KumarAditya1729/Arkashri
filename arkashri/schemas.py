# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arkashri.models import (
    ApprovalActionType,
    ApprovalStatus,
    AuditOpinionType,
    AuditRunStatus,
    AuditStepStatus,
    ClientRole,
    EngagementStatus,
    EngagementType,
    ExceptionStatus,
    IngestRunStatus,
    KnowledgeSourceType,
    MaterialityBasis,
    ModelStatus,
    RegulatorySourceType,
    ReportStatus,
    SignalType,
    FrameworkType,
    StandardsFramework,
    PolicyEnforcementAction,
    CrisisTriggerType,
    CrisisStatus,
    ContinuousAuditAction,
    InvestigationType,
    ESGCategory,
    ArchiveStatus,
)


class RuleCreate(BaseModel):
    rule_key: str = Field(min_length=1, max_length=100)
    version: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    expression: dict[str, Any]
    signal_value: float = Field(default=1.0, ge=0)
    severity_floor: float = Field(default=0.0, ge=0, le=100)
    is_active: bool = False


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_key: str
    version: int
    name: str
    description: str | None
    expression: dict[str, Any]
    signal_value: float
    severity_floor: float
    is_active: bool
    created_at: datetime


class FormulaCreate(BaseModel):
    version: int = Field(gt=0)
    formula_text: str
    component_caps: dict[str, float] = Field(
        default_factory=lambda: {"DETERMINISTIC": 0.7, "ML": 0.2, "TREND": 0.1}
    )
    is_active: bool = False


class FormulaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    formula_text: str
    formula_hash: str
    component_caps: dict[str, float]
    is_active: bool
    created_at: datetime


class WeightEntryInput(BaseModel):
    signal_type: SignalType
    signal_key: str = Field(min_length=1, max_length=128)
    weight: float = Field(ge=0)


class WeightSetCreate(BaseModel):
    version: int = Field(gt=0)
    entries: list[WeightEntryInput]
    is_active: bool = False


class WeightEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_type: SignalType
    signal_key: str
    weight: float


class WeightSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    weight_hash: str
    is_active: bool
    created_at: datetime
    entries: list[WeightEntryOut]


class ModelCreate(BaseModel):
    model_key: str = Field(min_length=1, max_length=100)
    version: int = Field(gt=0)
    purpose: str = Field(min_length=1, max_length=255)
    artifact_hash: str = Field(min_length=64, max_length=64)
    hyperparams_hash: str = Field(min_length=64, max_length=64)
    dataset_fingerprint: str = Field(min_length=64, max_length=64)
    feature_schema_hash: str = Field(min_length=64, max_length=64)
    metrics: dict[str, Any] = Field(default_factory=dict)
    fairness_metrics: dict[str, Any] = Field(default_factory=dict)
    status: ModelStatus = ModelStatus.SHADOW
    lower_bound: float = 0.0
    upper_bound: float = 1.0


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_key: str
    version: int
    purpose: str
    artifact_hash: str
    hyperparams_hash: str
    dataset_fingerprint: str
    feature_schema_hash: str
    metrics: dict[str, Any]
    fairness_metrics: dict[str, Any]
    status: ModelStatus
    lower_bound: float
    upper_bound: float
    created_at: datetime


class SignalInput(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: float
    lower_bound: float = 0.0
    upper_bound: float = 1.0
    model_key: str | None = None
    model_version: int | None = None


class TransactionScoreRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    payload: dict[str, Any]
    ml_signals: list[SignalInput] = Field(default_factory=list)
    trend_signals: list[SignalInput] = Field(default_factory=list)
    model_stability: float = Field(default=1.0, ge=0.0, le=1.0)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    final_risk: float
    confidence: float
    formula_version: int
    weight_set_version: int
    model_versions: list[dict[str, Any]]
    rule_snapshot: list[dict[str, Any]]
    explanation: dict[str, Any]
    trace_log: list[str] | None
    output_hash: str
    created_at: datetime


class DecisionOverrideCreate(BaseModel):
    overridden_risk_score: float = Field(ge=0.0)
    override_reason: str = Field(min_length=1, max_length=4000)
    reviewer_confirmation: bool = False


class DecisionOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    decision_id: uuid.UUID
    original_risk_score: float
    original_confidence: float
    overridden_risk_score: float
    overridden_by_user: str
    override_reason: str
    reviewer_confirmation: bool
    override_timestamp: datetime


class ReplayResponse(BaseModel):
    decision_id: uuid.UUID
    match: bool
    expected_hash: str
    actual_hash: str
    recomputed_risk: float


class AuditVerifyResponse(BaseModel):
    tenant_id: str
    jurisdiction: str
    is_valid: bool
    issues: list[str]
    event_count: int


class ExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    decision_id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    reason_code: str
    status: ExceptionStatus
    opened_at: datetime
    resolved_at: datetime | None
    sla_due_at: datetime
    notes: str | None


class ExceptionResolveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_key: str
    name: str
    domain: str
    is_active: bool
    created_at: datetime


class AgentBootstrapResponse(BaseModel):
    inserted: int
    total_active: int


class ReportGenerateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    period_start: datetime
    period_end: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    period_start: datetime
    period_end: datetime
    status: ReportStatus
    report_hash: str
    report_payload: dict[str, Any]
    created_at: datetime


class ChainAnchorRequest(BaseModel):
    anchor_provider: str = Field(default="POLKADOT", min_length=1, max_length=100)
    external_reference: str | None = Field(default=None, max_length=255)


class ChainAnchorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    jurisdiction: str
    window_start_event_id: int
    window_end_event_id: int
    merkle_root: str
    anchor_provider: str
    external_reference: str | None
    created_at: datetime


class CoverageOut(BaseModel):
    tenant_id: str
    jurisdiction: str
    transactions_received: int
    decisions_computed: int
    coverage_rate: float


class ScorecardOut(BaseModel):
    tenant_id: str
    jurisdiction: str
    automation_rate: float
    audit_cycle_days: float | None
    coverage_rate: float
    evidence_coverage_rate: float
    active_ai_agents: int
    blockchain_verification: bool
    realtime_collaboration: bool
    exception_first: bool
    ml_powered_fraud_detection: bool
    report_automation: bool
    scalability_target: str
    setup_time_days: int


class SystemBootstrapResponse(BaseModel):
    formula_created: bool
    rule_created: bool
    weight_set_created: bool
    model_created: bool
    agents_inserted: int


class WorkflowPackTemplateRef(BaseModel):
    audit_type: str
    path: str


class WorkflowPackIndexOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pack_id: str
    version: str
    schema_path: str = Field(alias="schema")
    templates: list[WorkflowPackTemplateRef]


class WorkflowTemplateOut(BaseModel):
    audit_type: str
    template: dict[str, Any]


class OrchestrationRunCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    audit_type: str = Field(min_length=1, max_length=64)
    created_by: str = Field(min_length=1, max_length=100)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    auto_execute: bool = False


class OrchestrationStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_no: int
    phase_id: str
    phase_name: str
    step_id: str
    action: str
    owner_role: str
    agent_key: str | None
    requires_approval: bool
    status: AuditStepStatus
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    evidence_payload: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class OrchestrationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    audit_type: str
    workflow_id: str
    workflow_version: str
    status: AuditRunStatus
    status_reason: str | None
    run_hash: str
    input_payload: dict[str, Any]
    created_by: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    steps: list[OrchestrationStepOut]


class OrchestrationExecuteRequest(BaseModel):
    max_steps: int = Field(default=50, ge=1, le=500)


class OrchestrationExecuteResponse(BaseModel):
    run_id: uuid.UUID
    job_id: str | None = None
    executed_steps: int | None = None
    blocked_steps: int | None = None
    pending_steps: int | None = None
    status: AuditRunStatus


class ApprovalRequestCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    request_type: str = Field(min_length=1, max_length=64)
    reference_type: str = Field(min_length=1, max_length=64)
    reference_id: str = Field(min_length=1, max_length=128)
    requested_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)
    required_level: int = Field(default=1, ge=1, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)
    step_id: uuid.UUID | None = None


class ApprovalActionCreate(BaseModel):
    action_type: ApprovalActionType
    actor_id: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    action_payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: uuid.UUID
    action_type: ApprovalActionType
    actor_id: str
    notes: str | None
    action_payload: dict[str, Any]
    created_at: datetime


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    request_type: str
    reference_type: str
    reference_id: str
    requested_by: str
    reason: str
    current_level: int
    required_level: int
    status: ApprovalStatus
    payload: dict[str, Any]
    decision_notes: str | None
    step_id: uuid.UUID | None
    opened_at: datetime
    closed_at: datetime | None
    actions: list[ApprovalActionOut]


class KnowledgeDocumentCreate(BaseModel):
    document_key: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    source_type: KnowledgeSourceType
    version: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_key: str
    jurisdiction: str
    source_type: KnowledgeSourceType
    version: int
    title: str
    content_hash: str
    metadata_json: dict[str, Any]
    is_active: bool
    created_at: datetime


class RagQueryRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    query_text: str = Field(min_length=1, max_length=4000)
    audit_type: str | None = Field(default=None, max_length=64)
    top_k: int = Field(default=5, ge=1, le=20)


class RagSourceOut(BaseModel):
    document_key: str
    document_title: str
    document_version: int
    jurisdiction: str
    chunk_index: int
    chunk_hash: str
    score: float
    snippet: str


class RagQueryResponse(BaseModel):
    query_hash: str
    answer: str
    sources: list[RagSourceOut]


class BlockchainAdapterOut(BaseModel):
    adapter_key: str
    network: str


class BlockchainAnchorRequest(BaseModel):
    adapter_key: str = Field(default="POLKADOT", min_length=1, max_length=100)
    merkle_root: str = Field(min_length=64, max_length=130)
    window_start_event_id: int = Field(ge=0)
    window_end_event_id: int = Field(ge=0)
    chain_anchor_id: int = Field(ge=0)
    external_reference: str | None = Field(default=None, max_length=255)


class ChainAttestationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain_anchor_id: int
    adapter_key: str
    network: str
    tx_reference: str
    attestation_hash: str
    provider_payload: dict[str, Any]
    created_at: datetime


class ApiClientBootstrapRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiClientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: ClientRole = ClientRole.OPERATOR


class ApiClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: ClientRole
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiClientCreateResponse(BaseModel):
    client: ApiClientOut
    api_key: str


class ApprovalEscalationResponse(BaseModel):
    tenant_id: str
    jurisdiction: str
    escalated_count: int
    escalated_request_ids: list[uuid.UUID]


class RegulatorySourceCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=120)
    jurisdiction: str = Field(min_length=2, max_length=20)
    authority: str = Field(min_length=1, max_length=120)
    source_type: RegulatorySourceType
    endpoint: str = Field(min_length=1, max_length=1024)
    parser_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class RegulatorySourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    jurisdiction: str
    authority: str
    source_type: RegulatorySourceType
    endpoint: str
    parser_config: dict[str, Any]
    is_active: bool
    last_success_at: datetime | None
    created_at: datetime


class RegulatorySourceBootstrapResponse(BaseModel):
    inserted: int
    existing: int


class RegulatoryIngestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: int
    status: IngestRunStatus
    fetched_count: int
    inserted_count: int
    error_message: str | None
    started_at: datetime
    ended_at: datetime | None


class RegulatorySyncResponse(BaseModel):
    runs: list[RegulatoryIngestRunOut]


class RegulatoryDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    jurisdiction: str
    authority: str
    external_id: str
    title: str
    summary: str | None
    document_url: str
    published_on: datetime | None
    content_hash: str
    metadata_json: dict[str, Any]
    is_promoted: bool
    promoted_knowledge_doc_id: int | None
    ingested_at: datetime


class RegulatoryPromoteRequest(BaseModel):
    source_type: KnowledgeSourceType = KnowledgeSourceType.LAW


class RegulatoryPromoteResponse(BaseModel):
    regulatory_document_id: int
    knowledge_document_id: int


class EngagementCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    client_name: str = Field(min_length=1, max_length=255)
    engagement_type: EngagementType = EngagementType.STATUTORY_AUDIT
    period_start: datetime | None = None
    period_end: datetime | None = None
    independence_cleared: bool | None = None
    kyc_cleared: bool | None = None
    conflict_check_notes: str | None = None


class EngagementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    standards_framework: StandardsFramework
    client_name: str
    engagement_type: EngagementType
    period_start: datetime | None
    period_end: datetime | None
    status: EngagementStatus
    independence_cleared: bool
    kyc_cleared: bool
    conflict_check_notes: str | None
    created_at: datetime
    updated_at: datetime


class MaterialityCreate(BaseModel):
    basis: MaterialityBasis
    basis_amount: float = Field(gt=0)
    overall_percentage: float = Field(gt=0, lt=100)
    performance_percentage: float = Field(gt=0, lt=100)
    trivial_threshold_percentage: float = Field(gt=0, lt=100)
    notes: str | None = None


class MaterialityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    basis: MaterialityBasis
    basis_amount: float
    overall_percentage: float
    overall_materiality: float
    performance_percentage: float
    performance_materiality: float
    trivial_threshold_percentage: float
    trivial_threshold: float
    notes: str | None
    created_at: datetime


class OpinionCreate(BaseModel):
    pass


class OpinionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: str
    jurisdiction: str
    opinion_type: AuditOpinionType
    basis_for_opinion: str
    key_audit_matters: dict[str, Any]
    is_signed: bool
    signed_by: str | None
    signature_hash: str | None
    created_at: datetime
    signed_at: datetime | None


class RegulatoryFrameworkCreate(BaseModel):
    jurisdiction: str = Field(min_length=2, max_length=20)
    framework_type: FrameworkType = FrameworkType.IFRS
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    authority: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class RegulatoryFrameworkOut(RegulatoryFrameworkCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CrossBorderPolicyCreate(BaseModel):
    source_jurisdiction: str = Field(min_length=2, max_length=20)
    target_jurisdiction: str = Field(min_length=2, max_length=20)
    policy_name: str = Field(min_length=1, max_length=255)
    enforcement_action: PolicyEnforcementAction = PolicyEnforcementAction.WARN
    constraint_details: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class CrossBorderPolicyOut(CrossBorderPolicyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class AuditPlaybookCreate(BaseModel):
    audit_type: EngagementType
    sector: str | None = Field(default=None, max_length=100)
    playbook_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    workflow_template_id: str = Field(min_length=1, max_length=128)
    required_phases: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    version: int = Field(gt=0, default=1)


class AuditPlaybookOut(AuditPlaybookCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SectorControlCreate(BaseModel):
    sector: str = Field(min_length=1, max_length=100)
    control_code: str = Field(min_length=1, max_length=100)
    control_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    risk_mapping: dict[str, Any] = Field(default_factory=dict)
    test_procedures: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SectorControlOut(SectorControlCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CrisisEventCreate(BaseModel):
    engagement_id: uuid.UUID
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    trigger_type: CrisisTriggerType
    status: CrisisStatus = CrisisStatus.ACTIVE
    escalated_by: str = Field(min_length=1, max_length=100)
    notes: str | None = None


class CrisisEventOut(CrisisEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    freeze_timestamp: datetime
    created_at: datetime
    updated_at: datetime


class ContinuousAuditRuleCreate(BaseModel):
    engagement_id: uuid.UUID
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    rule_name: str = Field(min_length=1, max_length=255)
    data_source_type: str = Field(min_length=1, max_length=50)
    frequency_minutes: int = Field(gt=0, default=60)
    threshold_value: float
    action_on_breach: ContinuousAuditAction
    is_active: bool = True


class ContinuousAuditRuleOut(ContinuousAuditRuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class ForensicInvestigationCreate(BaseModel):
    engagement_id: uuid.UUID
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    target_entity: str = Field(min_length=1, max_length=255)
    investigation_type: InvestigationType
    findings: dict[str, Any] = Field(default_factory=dict)
    risk_score: float = Field(default=0.0, ge=0.0)


class ForensicInvestigationOut(ForensicInvestigationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ESGMetricCreate(BaseModel):
    engagement_id: uuid.UUID
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    metric_category: ESGCategory
    metric_name: str = Field(min_length=1, max_length=255)
    value: float
    unit: str = Field(min_length=1, max_length=50)
    validation_source: str | None = None


class ESGMetricOut(ESGMetricCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class AIGovernanceLogCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    decision_id: str = Field(min_length=1, max_length=100)
    model_used: str = Field(min_length=1, max_length=100)
    decision_rationale: str = Field(min_length=1)
    human_override: bool = False
    override_reason: str | None = None


class AIGovernanceLogOut(AIGovernanceLogCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class SovereignArchiveCreate(BaseModel):
    engagement_id: uuid.UUID
    tenant_id: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=20)
    archive_hash: str = Field(min_length=64, max_length=64)
    status: ArchiveStatus = ArchiveStatus.PENDING
    archive_location: str = Field(min_length=1, max_length=500)
    retention_period_years: int = Field(gt=0, default=10)


class SovereignArchiveOut(SovereignArchiveCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class ESGMetricsCreate(BaseModel):
    carbon_footprint_scope_1: float | None = Field(default=None, ge=0.0)
    carbon_footprint_scope_2: float | None = Field(default=None, ge=0.0)
    carbon_footprint_scope_3: float | None = Field(default=None, ge=0.0)
    board_diversity_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    supply_chain_transparency_index: float | None = Field(default=None, ge=0.0, le=1.0)
    active_regulatory_fines: bool = False


class ESGMetricsOut(ESGMetricsCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    engagement_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ForensicProfileCreate(BaseModel):
    transaction_velocity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    benfords_law_deviation: float | None = Field(default=None, ge=0.0, le=1.0)
    offshore_routing_instances: int | None = Field(default=None, ge=0)
    ubo_opacity_index: float | None = Field(default=None, ge=0.0, le=1.0)
    sanctions_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)


class ForensicProfileOut(ForensicProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    engagement_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

class SystemAuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    user_id: uuid.UUID | None
    user_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    status: str
    extra_metadata: dict[str, Any] | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
