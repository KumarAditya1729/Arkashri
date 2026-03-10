import { AuditShell } from '@/components/layout/AuditShell'
import { PlaybookRenderer } from '@/components/audit/PlaybookRenderer'
import { PhaseApprovalGateway } from '@/components/audit/PhaseApprovalGateway'
import { EngagementStateInitializer } from '@/components/audit/EngagementStateInitializer'
import { WidgetErrorBoundary } from '@/components/layout/WidgetErrorBoundary'
import { AuditCompletionEstimator } from '@/components/audit/AuditCompletionEstimator'
import PartnerSignOff from '@/components/audit/PartnerSignOff'
import { getEngagement } from '@/lib/api'
import { registryByShortId } from '@/lib/engagementRegistry'

// ─── Local fallback registry ──────────────────────────────────────────────────
// Used when the backend is unavailable or the engagement is not yet seeded.
const LOCAL_REGISTRY: Record<string, { auditType: string; modules: { type: string }[] }> = {}

const DEFAULT_PLAYBOOK = { auditType: 'Audit Engagement', modules: [{ type: 'RiskModule' }] }

const TYPE_BADGE_COLORS: Record<string, string> = {
    'Forensic Audit': 'bg-red-100 text-red-800',
    'Financial Audit': 'bg-blue-100 text-blue-800',
    'ESG Audit': 'bg-green-100 text-green-800',
    'Internal Audit': 'bg-indigo-100 text-indigo-800',
    'External Audit': 'bg-purple-100 text-purple-800',
    'Statutory Audit': 'bg-teal-100 text-teal-800',
    'Tax Audit': 'bg-orange-100 text-orange-800',
    'Compliance Audit': 'bg-cyan-100 text-cyan-800',
    'Operational Audit': 'bg-amber-100 text-amber-800',
    'IT Audit': 'bg-sky-100 text-sky-800',
    'Payroll Audit': 'bg-pink-100 text-pink-800',
    'Performance Audit': 'bg-lime-100 text-lime-800',
    'Quality Audit': 'bg-rose-100 text-rose-800',
    'Environmental Audit': 'bg-emerald-100 text-emerald-800',
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default async function EngagementPage({ params }: { params: Promise<{ id: string }> }) {
    const { id: shortId } = await params

    // 1. Look up UUID from registry
    const registryEntry = registryByShortId(shortId)
    const uuid = registryEntry?.uuid ?? null

    // 2. Try to fetch live data from the backend
    type LiveData = {
        auditType: string
        clientName: string
        status: string
        sealHash: string | null
        sealedAt: string | null
        jurisdiction: string
        createdAt: string | null
        isLive: true
    }
    type LocalData = {
        auditType: string
        clientName: string
        status: string
        sealHash: null
        sealedAt: null
        jurisdiction: string
        createdAt: null
        isLive: false
    }
    type EngagementData = LiveData | LocalData

    let engagementData: EngagementData
    let fetchError: string | null = null

    if (uuid) {
        try {
            const liveEng = await getEngagement(uuid)
            if (liveEng) {
                engagementData = {
                    auditType: liveEng.engagement_type,
                    clientName: liveEng.client_name,
                    status: liveEng.status,
                    sealHash: liveEng.seal_hash,
                    sealedAt: liveEng.sealed_at,
                    jurisdiction: liveEng.jurisdiction,
                    createdAt: liveEng.created_at,
                    isLive: true,
                }
            } else {
                // 404 — not yet seeded
                fetchError = 'Engagement not found in DB. Run seed_engagements.py.'
                engagementData = buildLocalFallback(shortId, registryEntry)
            }
        } catch {
            fetchError = 'Backend unreachable. Showing local data.'
            engagementData = buildLocalFallback(shortId, registryEntry)
        }
    } else {
        // No UUID yet — local mode
        engagementData = buildLocalFallback(shortId, registryEntry)
    }

    const playbook = LOCAL_REGISTRY[shortId] ?? DEFAULT_PLAYBOOK
    const badgeClass = TYPE_BADGE_COLORS[engagementData.auditType] ?? 'bg-gray-100 text-gray-800'

    return (
        <AuditShell>
            <EngagementStateInitializer engagementId={shortId} auditType={engagementData.auditType} />

            <div className="mb-8 flex justify-between items-start">
                <div>
                    <div className="text-sm font-semibold text-gray-500 mb-2">ENGAGEMENT COMMAND CENTER</div>
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${badgeClass}`}>
                            {engagementData.auditType}
                        </span>

                        {/* LIVE / LOCAL data source badge */}
                        {engagementData.isLive ? (
                            <span className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                                LIVE
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 border border-gray-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
                                LOCAL
                            </span>
                        )}

                        {engagementData.sealedAt && (
                            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200">
                                🔒 SEALED
                            </span>
                        )}
                    </div>
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">
                        {engagementData.clientName}
                        <span className="text-gray-400 font-mono text-xl ml-3">ENG-{shortId}</span>
                    </h1>
                    {engagementData.isLive && (
                        <p className="text-sm text-gray-500 mt-1">
                            {engagementData.jurisdiction} · Status: <span className="font-semibold text-gray-700">{engagementData.status}</span>
                        </p>
                    )}

                    {/* Non-blocking fetch warning */}
                    {fetchError && (
                        <div className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
                            ⚠️ {fetchError}
                        </div>
                    )}
                </div>

                <div className="text-right shrink-0">
                    <div className="text-sm text-gray-500 mb-1">Status</div>
                    <div className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        {engagementData.status ?? 'Active Collection'}
                    </div>
                </div>
            </div>

            <WidgetErrorBoundary fallback={<div className="font-mono text-red-500 bg-red-50 p-4 border border-red-200">System Error: Playbook failed to render.</div>}>
                <PlaybookRenderer playbook={playbook} />
            </WidgetErrorBoundary>

            <WidgetErrorBoundary fallback={<div className="font-mono text-red-500 bg-red-50 p-4 border border-red-200">System Error: Gateway offline.</div>}>
                <PhaseApprovalGateway
                    currentPhase="Evidence Collection"
                    onApprove={async () => {
                        'use server'
                        console.log("Phase advanced via Server Action")
                    }}
                />
            </WidgetErrorBoundary>

            {/* ── Completion Estimator ── */}
            <AuditCompletionEstimator
                auditType={engagementData.auditType}
                status={engagementData.status}
                startDate={engagementData.createdAt ?? undefined}
            />

            {/* Multi-Partner Sign-Off & Seal */}
            {uuid ? (
                <PartnerSignOff
                    engagementId={uuid}
                    currentUserId="partner_001"
                    currentUserEmail=""
                    isPartner={true}
                    onSealed={(hash) => console.log('Sealed:', hash)}
                />
            ) : (
                <div className="mt-8 border-t pt-6">
                    <div className="text-xs text-gray-400 bg-gray-50 border border-dashed border-gray-200 rounded-lg p-4">
                        <span className="font-semibold text-gray-600">Partner Sign-Off & Seal</span> becomes available once
                        this engagement is seeded to the backend.
                        Run <code className="bg-gray-100 px-1 rounded">python3 scripts/seed_engagements.py</code> and update{' '}
                        <code className="bg-gray-100 px-1 rounded">lib/engagementRegistry.ts</code> with the returned UUIDs.
                    </div>
                </div>
            )}
        </AuditShell>
    )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildLocalFallback(
    shortId: string,
    entry: ReturnType<typeof registryByShortId>,
): { auditType: string; clientName: string; status: string; sealHash: null; sealedAt: null; jurisdiction: string; createdAt: null; isLive: false } {
    const local = LOCAL_REGISTRY[shortId] ?? DEFAULT_PLAYBOOK
    return {
        auditType: local.auditType,
        clientName: entry?.client ?? 'Unknown Client',
        status: 'Active Collection',
        sealHash: null,
        sealedAt: null,
        jurisdiction: entry?.jurisdiction ?? 'IN',
        createdAt: null,
        isLive: false,
    }
}
