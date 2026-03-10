/**
 * Arkashri API Client — Phase 1 complete
 *
 * All calls include:
 *   - X-Arkashri-Tenant  (required for Postgres RLS)
 *   - X-Arkashri-Key     (when token is present in localStorage)
 *
 * Token lifecycle:
 *   - Obtained from POST /api/v1/token (sign-in)
 *   - Stored in localStorage as 'arkashri_token'
 *   - Cleared on sign-out
 */

const BASE_URL = '/api/proxy'
const TENANT = process.env.NEXT_PUBLIC_API_TENANT ?? 'default_tenant'

// Secure token management is handled server-side in /app/api/auth/login/route.ts

// Token is now managed securely via HttpOnly cookies in the Next.js proxy.
// No client-side token access required.
function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
    return {
        'Content-Type': 'application/json',
        'X-Arkashri-Tenant': TENANT,
        ...extra,
    }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const isFormData = init?.body instanceof FormData
    const h = isFormData
        ? { 'X-Arkashri-Tenant': TENANT }
        : buildHeaders()
    const res = await fetch(`${BASE_URL}${path}`, {
        ...init,
        headers: { ...h, ...(init?.headers as Record<string, string> | undefined ?? {}) },
    })
    if (!res.ok) {
        const text = await res.text().catch(() => res.statusText)
        throw new ApiError(res.status, text)
    }
    if (res.status === 204) return undefined as T
    return res.json() as Promise<T>
}

export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
        this.name = 'ApiError'
    }
}

export interface EvidenceLedgerEntry {
    id: number
    tenant_id: string
    jurisdiction: string
    window_start_event_id: number
    window_end_event_id: number
    merkle_root: string
    anchor_provider: string
    external_reference: string | null
    created_at: string
    attestations: {
        id: number
        adapter_key: string
        network: string
        tx_reference: string
        attestation_hash: string
        provider_payload: any
        created_at: string
    }[]
}

// ─── Auth Types ───────────────────────────────────────────────────────────────

export interface TokenResponse {
    access_token: string
    token_type: string
    expires_in: number
    user: {
        email: string
        full_name: string
        role: string
        tenant_id: string
        initials: string
    }
}

// ─── Engagement Types ─────────────────────────────────────────────────────────

export type EngagementStatus = 'ACCEPTED' | 'UNDER_REVIEW' | 'REJECTED' | 'PLANNING' | 'FIELD_WORK' | 'REVIEW' | 'COMPLETED' | 'SEALED'

export interface EngagementResponse {
    id: string
    tenant_id: string
    jurisdiction: string
    client_name: string
    engagement_type: string
    status: EngagementStatus
    independence_cleared: boolean
    kyc_cleared: boolean
    conflict_check_notes: string | null
    sealed_at: string | null
    seal_hash: string | null
    created_at: string
}

export interface EngagementCreate {
    tenant_id: string
    jurisdiction: string
    client_name: string
    engagement_type: string
}

// ─── Seal Types ───────────────────────────────────────────────────────────────

export interface SealResponse {
    status: string
    message: string
    seal: {
        payload: {
            metadata: {
                seal_timestamp_utc: string
                engagement_id: string
                system_version: string
                tenant_id: string
                jurisdiction: string
            }
            opinion: { type: string; basis: string; is_signed: boolean }
            engine_state: { rule_snapshot_hash: string; weight_set_version: number; regulation_version_tag: string }
            cryptographic_anchors: { audit_event_merkle_root: string | null; decision_hash_tree_root: string }
        }
        hash: string
        signature: string
        signer: string
    }
}

// ─── Risk Types ───────────────────────────────────────────────────────────────

export type RiskLikelihood = 'High' | 'Medium' | 'Low'
export type RiskImpact = 'Critical' | 'High' | 'Medium' | 'Low'
export type RiskStatus = 'Open' | 'In Review' | 'Mitigated' | 'Accepted'

export interface RiskResponse {
    id: string
    engagement_id: string
    risk_ref: string
    title: string
    area: string
    likelihood: RiskLikelihood
    impact: RiskImpact
    risk_score: number
    owner: string
    control_ref: string | null
    risk_status: RiskStatus
    created_at: string
    updated_at: string
}

export interface RiskCreate {
    title: string
    area: string
    likelihood: RiskLikelihood
    impact: RiskImpact
    owner: string
    control_ref?: string
}

// ─── Evidence Types ───────────────────────────────────────────────────────────

export interface EvidenceResponse {
    id: string
    engagement_id: string
    evd_ref: string
    file_name: string
    file_path: string
    file_size_kb: string | null
    evidence_type: string
    test_ref: string | null
    uploaded_by: string
    ev_status: string
    uploaded_at: string
}

// ─── Approval Types ───────────────────────────────────────────────────────────

export interface ApprovalAction {
    id: string
    action_type: string
    actor_id: string
    notes: string | null
    created_at: string
}

export interface ApprovalResponse {
    id: string
    tenant_id: string
    jurisdiction: string
    request_type: string
    reference_type: string
    reference_id: string
    requested_by: string
    reason: string | null
    status: string
    current_level: number
    required_level: number
    opened_at: string
    closed_at: string | null
    decision_notes: string | null
    actions: ApprovalAction[]
}

// ─── Regulatory Types ─────────────────────────────────────────────────────────

export interface RegulatoryDoc {
    id: number
    jurisdiction: string
    title: string
    issuer: string
    source_url: string | null
    is_promoted: boolean
    ingested_at: string
    content: string | null
}

// ─── API Functions ────────────────────────────────────────────────────────────

// Auth - Now uses Next.js Route Handlers for HttpOnly cookies
export async function signIn(email: string, password: string): Promise<TokenResponse> {
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
        const text = await res.text()
        throw new ApiError(res.status, text)
    }
    return res.json()
}

export async function clearAuth(): Promise<void> {
    await fetch('/api/auth/logout', { method: 'POST' })
}

// Engagements
export async function getEngagement(uuid: string): Promise<EngagementResponse | null> {
    try {
        return await apiFetch<EngagementResponse>(`/api/v1/engagements/engagements/${uuid}`)
    } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
    }
}

export async function getEngagements(): Promise<EngagementResponse[]> {
    try {
        return await apiFetch<EngagementResponse[]>('/api/v1/engagements/engagements')
    } catch {
        return []
    }
}

export async function createEngagement(payload: EngagementCreate): Promise<EngagementResponse> {
    return apiFetch<EngagementResponse>('/api/v1/engagements/engagements', { method: 'POST', body: JSON.stringify(payload) })
}

export async function sealEngagement(uuid: string): Promise<SealResponse> {
    return apiFetch<SealResponse>(`/api/v1/engagements/engagements/${uuid}/seal`, { method: 'POST' })
}

// Risks
export async function getRisks(engagementUuid: string): Promise<RiskResponse[]> {
    try {
        return await apiFetch<RiskResponse[]>(`/api/v1/engagements/${engagementUuid}/risks`)
    } catch {
        return []
    }
}

export async function createRisk(engagementUuid: string, payload: RiskCreate): Promise<RiskResponse> {
    return apiFetch<RiskResponse>(`/api/v1/engagements/${engagementUuid}/risks`, {
        method: 'POST',
        body: JSON.stringify(payload),
    })
}

export async function updateRiskStatus(engagementUuid: string, riskId: string, status: RiskStatus): Promise<RiskResponse> {
    return apiFetch<RiskResponse>(`/api/v1/engagements/${engagementUuid}/risks/${riskId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
    })
}

// Evidence
export async function listEvidence(engagementUuid: string): Promise<EvidenceResponse[]> {
    try {
        return await apiFetch<EvidenceResponse[]>(`/api/v1/engagements/${engagementUuid}/evidence`)
    } catch {
        return []
    }
}

export async function uploadEvidence(engagementUuid: string, file: File, testRef?: string): Promise<EvidenceResponse> {
    const fd = new FormData()
    fd.append('file', file)
    if (testRef) fd.append('test_ref', testRef)
    return apiFetch<EvidenceResponse>(`/api/v1/engagements/${engagementUuid}/evidence`, {
        method: 'POST',
        body: fd,
    })
}

export async function deleteEvidence(engagementUuid: string, evidenceId: string): Promise<void> {
    return apiFetch<void>(`/api/v1/engagements/${engagementUuid}/evidence/${evidenceId}`, { method: 'DELETE' })
}

// Approvals
export async function getApprovals(tenant: string = TENANT, jurisdiction: string = 'IN'): Promise<ApprovalResponse[]> {
    try {
        return await apiFetch<ApprovalResponse[]>(`/api/v1/approvals/${tenant}/${jurisdiction}`)
    } catch {
        return []
    }
}

export async function actionApproval(requestId: string, actionType: 'APPROVED' | 'REJECTED' | 'COMMENTED', notes?: string): Promise<ApprovalResponse> {
    return apiFetch<ApprovalResponse>(`/api/v1/approvals/requests/${requestId}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action_type: actionType, notes: notes ?? null, action_payload: {} }),
    })
}

// Regulatory
export async function getRegulatoryDocuments(jurisdiction: string = 'IN'): Promise<RegulatoryDoc[]> {
    try {
        return await apiFetch<RegulatoryDoc[]>(`/api/v1/regulatory/documents/${jurisdiction}`)
    } catch {
        return []
    }
}

export async function promoteRegulatoryDoc(docId: number): Promise<void> {
    await apiFetch(`/api/v1/regulatory/documents/${docId}/promote`, {
        method: 'POST',
        body: JSON.stringify({ notes: 'Acknowledged via UI' }),
    })
}

// ─── Automation Score Types ───────────────────────────────────────────────────

export interface AutomationDimension {
    label: string
    score: number    // 0–100
    weight: number    // relative weight
    automated: number
    total: number
    description: string
}

export interface AutomationScoreResponse {
    overall_score: number
    grade: string    // A+, A, A−, B+, B, C
    tenant_id: string
    jurisdiction: string
    dimensions: AutomationDimension[]
    computed_at: string
    insight: string
}

// Baseline removed to ensure all data is live from backend

export async function getAutomationScore(
    tenant: string = TENANT,
    jurisdiction: string = 'IN',
): Promise<AutomationScoreResponse | null> {
    try {
        return await apiFetch<AutomationScoreResponse>(
            `/api/v1/reporting/metrics/automation-score?tenant_id=${tenant}&jurisdiction=${jurisdiction}`
        )
    } catch (err) {
        console.warn('Backend metrics unreachable. UI should handle stale state.', err)
        return null // Return null to allow UI to show stale vs live status
    }
}

// ─── Multi-Partner Seal Session Types ────────────────────────────────────────

export type SealSessionStatus = 'PENDING' | 'PARTIALLY_SIGNED' | 'FULLY_SIGNED' | 'WITHDRAWN'
export enum PartnerRole {
    ENGAGEMENT_PARTNER = 'ENGAGEMENT_PARTNER',
    EQCR_PARTNER = 'EQCR_PARTNER',
    COMPONENT_AUDITOR = 'COMPONENT_AUDITOR',
    JOINT_AUDITOR = 'JOINT_AUDITOR',
    REGULATORY_COSIGN = 'REGULATORY_COSIGN'
}

export interface SealSignatureOut {
    id: string
    partner_user_id: string
    partner_email: string
    role: PartnerRole
    jurisdiction: string
    override_count_acknowledged: number
    override_ack_confirmed: boolean
    signature_hash: string
    signed_at: string
    withdrawn_at: string | null
}

export interface SealSessionOut {
    id: string
    engagement_id: string
    required_signatures: number
    current_signature_count: number
    status: SealSessionStatus
    frozen_at: string | null
    created_by: string
    created_at: string
    signatures: SealSignatureOut[]
    can_seal: boolean
}

export interface PreSignSummary {
    engagement_id: string
    client_name: string
    engagement_type: string
    jurisdiction: string
    final_opinion_type: string
    basis_for_opinion: string
    weight_set_version: number | null
    rule_snapshot_hash: string | null
    system_version: string
    total_transactions_evaluated: number
    total_decisions: number
    open_exceptions: number
    resolved_exceptions: number
    total_ai_overrides: number
    session_id: string
    required_signatures: number
    current_signature_count: number
    status: SealSessionStatus
    signatures: SealSignatureOut[]
}

// ─── Seal Session API Functions ───────────────────────────────────────────────

export async function createSealSession(
    engagementUuid: string,
    requiredSignatures = 2,
    createdBy = 'system',
): Promise<SealSessionOut> {
    return apiFetch<SealSessionOut>(`/v1/engagements/${engagementUuid}/seal-session`, {
        method: 'POST',
        body: JSON.stringify({ required_signatures: requiredSignatures, created_by: createdBy }),
    })
}

export async function getSealSession(engagementUuid: string): Promise<SealSessionOut | null> {
    try {
        return await apiFetch<SealSessionOut>(`/v1/engagements/${engagementUuid}/seal-session`)
    } catch {
        return null
    }
}

export async function getPreSignSummary(sessionId: string): Promise<PreSignSummary | null> {
    try {
        return await apiFetch<PreSignSummary>(`/v1/seal-sessions/${sessionId}/pre-sign-summary`)
    } catch {
        return null
    }
}

export async function signSealSession(
    sessionId: string,
    partnerUserId: string,
    partnerEmail: string,
    role: PartnerRole,
    overrideAckConfirmed: boolean,
    overrideCountAcknowledged = 0,
    jurisdiction = 'IN',
): Promise<SealSessionOut> {
    return apiFetch<SealSessionOut>(`/v1/seal-sessions/${sessionId}/sign`, {
        method: 'POST',
        body: JSON.stringify({
            partner_user_id: partnerUserId,
            partner_email: partnerEmail,
            role,
            jurisdiction,
            override_count_acknowledged: overrideCountAcknowledged,
            override_ack_confirmed: overrideAckConfirmed,
        }),
    })
}

export async function withdrawSignature(
    sessionId: string,
    signatureId: string,
    withdrawalReason: string,
): Promise<SealSessionOut> {
    return apiFetch<SealSessionOut>(`/v1/seal-sessions/${sessionId}/signatures/${signatureId}`, {
        method: 'DELETE',
        body: JSON.stringify({ withdrawal_reason: withdrawalReason }),
    })
}
export async function getAdminEvidenceLedger(): Promise<EvidenceLedgerEntry[]> {
    return apiFetch<EvidenceLedgerEntry[]>("/v1/admin/evidence-ledger");
}
