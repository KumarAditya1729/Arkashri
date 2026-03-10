'use client'

/**
 * PartnerSignOff.tsx — Multi-Partner Co-Sign Component
 *
 * Implements mandatory partner sign-off before sealing.
 * Displays:
 *   1. Pre-sign checklist (opinion, exceptions, AI overrides, rule version)
 *   2. Signature progress (n / required)
 *   3. Override acknowledgement checkbox (mandatory if AI overrides exist)
 *   4. Sign & Seal button (disabled until checkbox ticked)
 *   5. Sealed state — hash + timestamp + full signature trail
 *
 * Architecture principle: AI assists. Partner decides.
 */

import { useEffect, useState, useCallback } from 'react'
import {
    ShieldCheck, Users, CheckCircle2, XCircle, AlertTriangle,
    Lock, Unlock, ChevronDown, ChevronUp, Eye, Fingerprint,
    FileCheck, Scale, AlertCircle, RefreshCcw, Trash2
} from 'lucide-react'
import {
    SealSessionOut, PreSignSummary, SealSignatureOut, PartnerRole,
    getSealSession, createSealSession, getPreSignSummary,
    signSealSession, withdrawSignature, sealEngagement,
} from '@/lib/api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
    engagementId: string       // UUID
    currentUserId?: string
    currentUserEmail?: string
    isPartner?: boolean        // whether the current user can sign
    onSealed?: (sealHash: string) => void
}

// ─── Role labels ─────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<PartnerRole, string> = {
    [PartnerRole.ENGAGEMENT_PARTNER]: 'Engagement Partner',
    [PartnerRole.EQCR_PARTNER]: 'EQCR Partner',
    [PartnerRole.COMPONENT_AUDITOR]: 'Component Auditor',
    [PartnerRole.JOINT_AUDITOR]: 'Joint Auditor',
    [PartnerRole.REGULATORY_COSIGN]: 'Regulatory Co-Sign',
}

const OPINION_COLORS: Record<string, string> = {
    UNMODIFIED: 'text-emerald-400',
    QUALIFIED: 'text-amber-400',
    ADVERSE: 'text-red-400',
    DISCLAIMER: 'text-slate-400',
    NONE: 'text-slate-500',
}

const OPINION_ICONS: Record<string, string> = {
    UNMODIFIED: '🟢',
    QUALIFIED: '🟡',
    ADVERSE: '🔴',
    DISCLAIMER: '⚪',
    NONE: '—',
}

// ─── Signature Avatar ─────────────────────────────────────────────────────────

function SignatureSlot({
    sig, index, required, onWithdraw
}: {
    sig?: SealSignatureOut
    index: number
    required: number
    onWithdraw?: (sigId: string) => void
}) {
    const isSigned = !!sig && !sig.withdrawn_at
    return (
        <div className={`flex flex-col items-center gap-2 transition-all duration-500
            ${isSigned ? 'opacity-100' : 'opacity-50'}`}>
            <div className={`w-14 h-14 rounded-full flex items-center justify-center border-2 transition-all duration-500
                ${isSigned
                    ? 'bg-emerald-500/20 border-emerald-500 shadow-[0_0_16px_rgba(16,185,129,0.4)]'
                    : 'bg-slate-800 border-slate-600 border-dashed'}`}>
                {isSigned
                    ? <Fingerprint className="w-6 h-6 text-emerald-400" />
                    : <span className="text-slate-500 text-sm font-bold">{index + 1}</span>
                }
            </div>
            {isSigned ? (
                <div className="text-center">
                    <p className="text-xs text-emerald-300 font-semibold">{sig!.partner_email.split('@')[0]}</p>
                    <p className="text-[10px] text-slate-400">{ROLE_LABELS[sig!.role]}</p>
                    <p className="text-[10px] text-slate-500">
                        {new Date(sig!.signed_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}
                    </p>
                    {onWithdraw && (
                        <button
                            onClick={() => onWithdraw(sig!.id)}
                            className="mt-1 text-[10px] text-red-400 hover:text-red-300 flex items-center gap-0.5 mx-auto"
                        >
                            <Trash2 className="w-2.5 h-2.5" /> Withdraw
                        </button>
                    )}
                </div>
            ) : (
                <p className="text-[10px] text-slate-500">Awaiting signature {index + 1}</p>
            )}
        </div>
    )
}

// ─── Pre-Sign Checklist Row ───────────────────────────────────────────────────

function CheckRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
    return (
        <div className="flex items-start justify-between py-2 border-b border-slate-800/60 last:border-0 gap-4">
            <span className="text-slate-400 text-sm flex-shrink-0">{label}</span>
            <span className={`text-sm font-mono text-right ${ok === false ? 'text-red-400' : ok === true ? 'text-emerald-400' : 'text-slate-200'}`}>
                {value}
            </span>
        </div>
    )
}

// ─── Main Component ────────────────────────────────────────────────────────────

export default function PartnerSignOff({
    engagementId, currentUserId = '',
    currentUserEmail = '', isPartner = true, onSealed,
}: Props) {
    const [session, setSession] = useState<SealSessionOut | null>(null)
    const [summary, setSummary] = useState<PreSignSummary | null>(null)
    const [loading, setLoading] = useState(true)
    const [signing, setSigning] = useState(false)
    const [sealing, setSealing] = useState(false)
    const [creating, setCreating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [sealResult, setSealResult] = useState<{ hash: string; sealedAt: string } | null>(null)
    const [expanded, setExpanded] = useState(true)

    // Sign form state
    const [role, setRole] = useState<PartnerRole>(PartnerRole.ENGAGEMENT_PARTNER)
    const [overrideAck, setOverrideAck] = useState(false)
    const [withdrawReason, setWithdrawReason] = useState('')
    const [withdrawingId, setWithdrawingId] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const sess = await getSealSession(engagementId)
            setSession(sess)
            if (sess) {
                const pre = await getPreSignSummary(sess.id)
                setSummary(pre)
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to load seal session.')
        } finally {
            setLoading(false)
        }
    }, [engagementId])

    useEffect(() => { load() }, [load])

    const handleCreate = async () => {
        setCreating(true)
        setError(null)
        try {
            const sess = await createSealSession(engagementId, 2, currentUserId)
            setSession(sess)
            const pre = await getPreSignSummary(sess.id)
            setSummary(pre)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to create seal session.')
        } finally {
            setCreating(false)
        }
    }

    const handleSign = async () => {
        if (!session) return
        if (summary && summary.total_ai_overrides > 0 && !overrideAck) {
            setError(`You must acknowledge ${summary.total_ai_overrides} AI override(s) before signing.`)
            return
        }
        setSigning(true)
        setError(null)
        try {
            const updated = await signSealSession(
                session.id, currentUserId, currentUserEmail,
                role, overrideAck,
                summary?.total_ai_overrides ?? 0,
                summary?.jurisdiction ?? 'IN',
            )
            setSession(updated)
            const pre = await getPreSignSummary(updated.id)
            setSummary(pre)
            setOverrideAck(false)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to submit signature.')
        } finally {
            setSigning(false)
        }
    }

    const handleSeal = async () => {
        if (!session?.can_seal) return
        setSealing(true)
        setError(null)
        try {
            const result = await sealEngagement(engagementId)
            const hash = (result as { hash?: string }).hash ?? (result as { seal?: { hash?: string } }).seal?.hash ?? 'sealed'
            const ts = new Date().toISOString()
            setSealResult({ hash, sealedAt: ts })
            onSealed?.(hash)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to seal engagement.')
        } finally {
            setSealing(false)
        }
    }

    const handleWithdraw = async (sigId: string) => {
        if (!session || !withdrawReason.trim()) {
            setError('Please provide a withdrawal reason.')
            return
        }
        try {
            const updated = await withdrawSignature(session.id, sigId, withdrawReason)
            setSession(updated)
            setWithdrawingId(null)
            setWithdrawReason('')
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to withdraw signature.')
        }
    }

    const alreadySigned = session?.signatures.some(
        s => s.partner_user_id === currentUserId && !s.withdrawn_at
    )

    // ── Sealed state ──────────────────────────────────────────────────────────
    if (sealResult) {
        return (
            <div className="rounded-2xl bg-emerald-950/30 border border-emerald-500/40 p-6
                shadow-[0_0_40px_rgba(16,185,129,0.15)] mt-6">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center
                        shadow-[0_0_20px_rgba(16,185,129,0.4)]">
                        <Lock className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-emerald-300">Engagement Sealed</h2>
                        <p className="text-xs text-slate-400">
                            {new Date(sealResult.sealedAt).toLocaleString('en-IN', { dateStyle: 'full', timeStyle: 'long' })}
                        </p>
                    </div>
                </div>
                <div className="bg-slate-900/60 rounded-xl p-4 font-mono text-xs break-all">
                    <p className="text-slate-400 mb-1">SHA-256 Seal Hash</p>
                    <p className="text-emerald-300">{sealResult.hash}</p>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                    This audit bundle is now WORM-locked. No further mutations are permitted.
                    The seal hash can be independently verified by any regulator.
                </p>
            </div>
        )
    }

    return (
        <div className="rounded-2xl bg-slate-900/60 border border-slate-700/50 mt-6 overflow-hidden">
            {/* Header */}
            <button
                onClick={() => setExpanded(x => !x)}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-slate-800/30 transition-colors"
            >
                <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center
                        ${session?.status === 'FULLY_SIGNED'
                            ? 'bg-emerald-500/20'
                            : session?.status === 'PARTIALLY_SIGNED'
                                ? 'bg-amber-500/20'
                                : 'bg-slate-700'}`}>
                        {session?.status === 'FULLY_SIGNED'
                            ? <ShieldCheck className="w-4 h-4 text-emerald-400" />
                            : <Unlock className="w-4 h-4 text-slate-400" />
                        }
                    </div>
                    <div className="text-left">
                        <p className="text-sm font-semibold text-slate-100">Partner Sign-Off</p>
                        <p className="text-xs text-slate-400">
                            {!session ? 'No session created' :
                                session.status === 'FULLY_SIGNED' ? 'Ready to seal' :
                                    session.status === 'PARTIALLY_SIGNED'
                                        ? `${session.current_signature_count}/${session.required_signatures} signatures`
                                        : `0/${session?.required_signatures ?? 2} signatures`}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {session?.status === 'FULLY_SIGNED' && (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-semibold">
                            FULLY SIGNED
                        </span>
                    )}
                    {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                </div>
            </button>

            {expanded && (
                <div className="px-6 pb-6 space-y-5">
                    {/* Error */}
                    {error && (
                        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-950/40 border border-red-500/30">
                            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-red-300">{error}</p>
                        </div>
                    )}

                    {loading ? (
                        <div className="flex items-center gap-2 py-4 text-slate-400">
                            <RefreshCcw className="w-4 h-4 animate-spin" />
                            <span className="text-sm">Loading seal session…</span>
                        </div>
                    ) : !session ? (
                        /* No session — create one */
                        <div className="space-y-4">
                            <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-950/30 border border-amber-500/30">
                                <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-sm text-amber-300 font-semibold">No seal session exists</p>
                                    <p className="text-xs text-slate-400 mt-0.5">
                                        Create a sign-off session to initiate multi-partner co-sign.
                                        Default requires 2 signatures (Engagement Partner + EQCR).
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={handleCreate}
                                disabled={creating}
                                className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50
                                    text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
                            >
                                {creating ? <RefreshCcw className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
                                {creating ? 'Creating…' : 'Create Seal Session (2 Signatures Required)'}
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-5">
                            {/* Signature Progress */}
                            <div>
                                <p className="text-xs text-slate-400 uppercase tracking-widest mb-3">
                                    Signature Progress — {session.current_signature_count}/{session.required_signatures} Partners
                                </p>
                                <div className="flex items-start gap-6 justify-center py-4">
                                    {Array.from({ length: session.required_signatures }).map((_, i) => (
                                        <SignatureSlot
                                            key={i}
                                            index={i}
                                            required={session.required_signatures}
                                            sig={session.signatures.filter(s => !s.withdrawn_at)[i]}
                                            onWithdraw={
                                                session.signatures.filter(s => !s.withdrawn_at)[i]?.partner_user_id === currentUserId
                                                    ? (id) => { setWithdrawingId(id); setError(null) }
                                                    : undefined
                                            }
                                        />
                                    ))}
                                </div>
                                {/* Progress bar */}
                                <div className="mt-2 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full rounded-full transition-all duration-700
                                            ${session.status === 'FULLY_SIGNED' ? 'bg-emerald-500' : 'bg-blue-500'}`}
                                        style={{ width: `${(session.current_signature_count / session.required_signatures) * 100}%` }}
                                    />
                                </div>
                            </div>

                            {/* Pre-sign Checklist */}
                            {summary && (
                                <div className="rounded-xl bg-slate-800/40 border border-slate-700/50 overflow-hidden">
                                    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-700/50 bg-slate-800/60">
                                        <Eye className="w-3.5 h-3.5 text-slate-400" />
                                        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                                            Pre-Sign Checklist — Partner Review
                                        </p>
                                    </div>
                                    <div className="px-4 py-2">
                                        <CheckRow label="Client" value={summary.client_name} />
                                        <CheckRow label="Engagement Type" value={summary.engagement_type.replace('_', ' ')} />
                                        <CheckRow label="Jurisdiction" value={summary.jurisdiction} />
                                        <CheckRow
                                            label="Final Opinion"
                                            value={`${OPINION_ICONS[summary.final_opinion_type] ?? '?'} ${summary.final_opinion_type}`}
                                            ok={summary.final_opinion_type === 'UNMODIFIED' ? true : summary.final_opinion_type === 'ADVERSE' ? false : undefined}
                                        />
                                        <CheckRow
                                            label="Open Exceptions"
                                            value={String(summary.open_exceptions)}
                                            ok={summary.open_exceptions === 0}
                                        />
                                        <CheckRow label="Resolved Exceptions" value={String(summary.resolved_exceptions)} />
                                        <CheckRow
                                            label="AI Overrides"
                                            value={summary.total_ai_overrides > 0
                                                ? `${summary.total_ai_overrides} (acknowledgement required)`
                                                : 'None'}
                                            ok={summary.total_ai_overrides === 0 ? true : undefined}
                                        />
                                        <CheckRow label="Transactions Evaluated" value={String(summary.total_decisions)} />
                                        <CheckRow
                                            label="Rule Snapshot"
                                            value={summary.rule_snapshot_hash
                                                ? summary.rule_snapshot_hash.slice(0, 16) + '…'
                                                : 'Not computed'}
                                        />
                                        <CheckRow
                                            label="Weight Set Version"
                                            value={summary.weight_set_version ? `v${summary.weight_set_version}` : 'N/A'}
                                        />
                                        <CheckRow label="System Version" value={summary.system_version} />
                                    </div>
                                </div>
                            )}

                            {/* Withdraw signature flow */}
                            {withdrawingId && (
                                <div className="rounded-xl bg-red-950/30 border border-red-500/30 p-4 space-y-3">
                                    <p className="text-sm text-red-300 font-semibold">Withdrawal Reason (mandatory)</p>
                                    <textarea
                                        value={withdrawReason}
                                        onChange={e => setWithdrawReason(e.target.value)}
                                        placeholder="Explain why you are withdrawing your signature…"
                                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-200
                                            placeholder-slate-500 resize-none h-20 focus:outline-none focus:border-red-500"
                                    />
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => handleWithdraw(withdrawingId)}
                                            disabled={withdrawReason.trim().length < 10}
                                            className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-40
                                                text-white text-sm font-semibold transition-colors"
                                        >
                                            Confirm Withdrawal
                                        </button>
                                        <button
                                            onClick={() => { setWithdrawingId(null); setWithdrawReason('') }}
                                            className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm transition-colors"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Sign section — only show if user hasn't signed yet and session isn't complete */}
                            {isPartner && !alreadySigned && session.status !== 'FULLY_SIGNED' && (
                                <div className="rounded-xl bg-slate-800/40 border border-slate-700/50 p-4 space-y-4">
                                    <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                                        <Fingerprint className="w-3.5 h-3.5" /> Your Signature
                                    </p>

                                    {/* Role selector */}
                                    <div>
                                        <label className="text-xs text-slate-400 mb-1.5 block">Your Role</label>
                                        <select
                                            value={role}
                                            onChange={e => setRole(e.target.value as PartnerRole)}
                                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm
                                                text-slate-200 focus:outline-none focus:border-blue-500"
                                        >
                                            {(Object.entries(ROLE_LABELS) as [PartnerRole, string][]).map(([k, v]) => (
                                                <option key={k} value={k}>{v}</option>
                                            ))}
                                        </select>
                                    </div>

                                    {/* Override ack — only shown if overrides exist */}
                                    {summary && summary.total_ai_overrides > 0 && (
                                        <label className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors
                                            ${overrideAck
                                                ? 'bg-blue-950/40 border-blue-500/40'
                                                : 'bg-amber-950/20 border-amber-500/30'}`}>
                                            <input
                                                type="checkbox"
                                                checked={overrideAck}
                                                onChange={e => setOverrideAck(e.target.checked)}
                                                className="mt-0.5 w-4 h-4 accent-blue-500 flex-shrink-0"
                                            />
                                            <div>
                                                <p className="text-sm text-slate-200 font-medium">
                                                    Override Acknowledgement
                                                </p>
                                                <p className="text-xs text-slate-400 mt-0.5">
                                                    I confirm that <strong className="text-amber-300">{summary.total_ai_overrides} AI-generated
                                                        risk assessment(s)</strong> were overridden and that I have reviewed
                                                    the documented professional justifications for each override.
                                                    (PCAOB AS 2301 — Professional Skepticism)
                                                </p>
                                            </div>
                                        </label>
                                    )}

                                    {/* Sign button */}
                                    <button
                                        onClick={handleSign}
                                        disabled={signing || (!!summary && summary.total_ai_overrides > 0 && !overrideAck)}
                                        className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40
                                            text-white font-semibold text-sm transition-all flex items-center justify-center gap-2
                                            shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:shadow-[0_0_30px_rgba(59,130,246,0.5)]"
                                    >
                                        {signing
                                            ? <><RefreshCcw className="w-4 h-4 animate-spin" /> Submitting…</>
                                            : <><Fingerprint className="w-4 h-4" /> Sign as {ROLE_LABELS[role]}</>
                                        }
                                    </button>
                                </div>
                            )}

                            {/* Already signed notice */}
                            {alreadySigned && session.status !== 'FULLY_SIGNED' && (
                                <div className="flex items-center gap-2 p-3 rounded-xl bg-blue-950/30 border border-blue-500/30">
                                    <CheckCircle2 className="w-4 h-4 text-blue-400 flex-shrink-0" />
                                    <p className="text-sm text-blue-300">
                                        You have signed. Awaiting {session.required_signatures - session.current_signature_count} more partner(s).
                                    </p>
                                </div>
                            )}

                            {/* Final Seal button — only when FULLY_SIGNED */}
                            {session.status === 'FULLY_SIGNED' && (
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/30">
                                        <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                                        <p className="text-sm text-emerald-300">
                                            All {session.required_signatures} partner signatures collected.
                                            The engagement is ready to be sealed.
                                        </p>
                                    </div>
                                    <button
                                        onClick={handleSeal}
                                        disabled={sealing}
                                        className="w-full py-3.5 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2
                                            bg-gradient-to-r from-emerald-600 to-teal-600
                                            hover:from-emerald-500 hover:to-teal-500
                                            disabled:opacity-50 text-white
                                            shadow-[0_0_30px_rgba(16,185,129,0.4)]
                                            hover:shadow-[0_0_40px_rgba(16,185,129,0.6)]"
                                    >
                                        {sealing
                                            ? <><RefreshCcw className="w-4 h-4 animate-spin" /> Generating WORM Seal…</>
                                            : <><Lock className="w-4 h-4" /> Generate Cryptographic Seal &amp; Lock Engagement</>
                                        }
                                    </button>
                                    <p className="text-[11px] text-slate-500 text-center">
                                        This action is irreversible. The engagement will be WORM-locked and marked SEALED.
                                    </p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
