'use client'

import { useEffect, useState, useRef } from 'react'
import { Calendar, Clock, TrendingUp, Zap, AlertTriangle, CheckCircle2 } from 'lucide-react'

// ─── Audit duration data (Arkashri-accelerated, in working days) ──────────────

const AUDIT_DURATIONS: Record<string, {
    traditional: number   // calendar days (traditional)
    arkashri: number      // calendar days (with Arkashri 93% automation)
    phases: { name: string; pct: number; days: number }[]
}> = {
    'Forensic Audit': { traditional: 270, arkashri: 42, phases: [{ name: 'Planning & Scope', pct: 10, days: 4 }, { name: 'Data Acquisition', pct: 20, days: 8 }, { name: 'Evidence Analysis', pct: 35, days: 15 }, { name: 'Exception Review', pct: 20, days: 8 }, { name: 'Report & Sign-off', pct: 15, days: 7 }] },
    'Financial Audit': { traditional: 120, arkashri: 28, phases: [{ name: 'Risk Assessment', pct: 15, days: 4 }, { name: 'Internal Control Test', pct: 20, days: 6 }, { name: 'Substantive Testing', pct: 35, days: 10 }, { name: 'Review & Approvals', pct: 20, days: 5 }, { name: 'Report & Sign-off', pct: 10, days: 3 }] },
    'Statutory Audit': { traditional: 150, arkashri: 30, phases: [{ name: 'Engagement Acceptance', pct: 10, days: 3 }, { name: 'Risk & Materiality', pct: 20, days: 6 }, { name: 'Substantive Procedures', pct: 40, days: 12 }, { name: 'CARO / Schedule III', pct: 20, days: 6 }, { name: 'Sign-off', pct: 10, days: 3 }] },
    'Tax Audit': { traditional: 45, arkashri: 7, phases: [{ name: 'Document Collection', pct: 20, days: 1 }, { name: 'Computation Review', pct: 40, days: 3 }, { name: 'Form 3CA/3CB Prep', pct: 25, days: 2 }, { name: 'Sign-off', pct: 15, days: 1 }] },
    'Compliance Audit': { traditional: 21, arkashri: 4, phases: [{ name: 'Control Mapping', pct: 25, days: 1 }, { name: 'Testing', pct: 45, days: 2 }, { name: 'Remediation Track', pct: 20, days: 1 }, { name: 'Report', pct: 10, days: 0 }] },
    'Internal Audit': { traditional: 30, arkashri: 10, phases: [{ name: 'Planning', pct: 15, days: 2 }, { name: 'Field Work', pct: 50, days: 5 }, { name: 'Review', pct: 25, days: 2 }, { name: 'Report', pct: 10, days: 1 }] },
    'IT Audit': { traditional: 49, arkashri: 18, phases: [{ name: 'Scope & Access', pct: 15, days: 3 }, { name: 'Control Testing', pct: 40, days: 7 }, { name: 'Vulnerability Review', pct: 30, days: 5 }, { name: 'Report', pct: 15, days: 3 }] },
    'ESG Audit': { traditional: 42, arkashri: 10, phases: [{ name: 'Data Collection', pct: 30, days: 3 }, { name: 'Emission Calc', pct: 35, days: 4 }, { name: 'Governance Review', pct: 25, days: 2 }, { name: 'Report', pct: 10, days: 1 }] },
    'Payroll Audit': { traditional: 14, arkashri: 3, phases: [{ name: 'Data Pull', pct: 25, days: 1 }, { name: 'Exception Review', pct: 50, days: 1 }, { name: 'Sign-off', pct: 25, days: 1 }] },
    'Operational Audit': { traditional: 35, arkashri: 12, phases: [{ name: 'Process Map', pct: 20, days: 2 }, { name: 'Field Observation', pct: 40, days: 5 }, { name: 'Gap Analysis', pct: 25, days: 3 }, { name: 'Report', pct: 15, days: 2 }] },
    'Performance Audit': { traditional: 60, arkashri: 18, phases: [{ name: 'KPI Baseline', pct: 20, days: 4 }, { name: 'Data Analysis', pct: 40, days: 7 }, { name: 'Benchmarking', pct: 25, days: 5 }, { name: 'Report', pct: 15, days: 2 }] },
    'Quality Audit': { traditional: 21, arkashri: 7, phases: [{ name: 'Standards Review', pct: 20, days: 1 }, { name: 'Process Audit', pct: 50, days: 4 }, { name: 'NCR Tracking', pct: 20, days: 1 }, { name: 'Sign-off', pct: 10, days: 1 }] },
    'Environmental Audit': { traditional: 42, arkashri: 10, phases: [{ name: 'Site Inspection', pct: 30, days: 3 }, { name: 'Compliance Check', pct: 40, days: 4 }, { name: 'Remediation Plan', pct: 20, days: 2 }, { name: 'Report', pct: 10, days: 1 }] },
}

const DEFAULT_DURATION = { traditional: 60, arkashri: 14, phases: [{ name: 'Field Work', pct: 60, days: 8 }, { name: 'Review', pct: 25, days: 4 }, { name: 'Sign-off', pct: 15, days: 2 }] }

// ─── Status → progress mapping ────────────────────────────────────────────────

const STATUS_PROGRESS: Record<string, number> = {
    'PLANNING': 10,
    'FIELD_WORK': 40,
    'REVIEW': 70,
    'COMPLETED': 100,
    'SEALED': 100,
    'ACCEPTED': 5,
    'UNDER_REVIEW': 55,
    'Active Collection': 40,
    'In Progress': 45,
    'Planning': 10,
    'Review': 70,
    'Completed': 100,
    'Not Started': 0,
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function addWorkingDays(date: Date, days: number): Date {
    const result = new Date(date)
    let added = 0
    while (added < days) {
        result.setDate(result.getDate() + 1)
        const dow = result.getDay()
        if (dow !== 0 && dow !== 6) added++
    }
    return result
}

function formatDate(d: Date): string {
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function daysUntil(d: Date): number {
    const now = new Date('2026-02-25T18:13:26+05:30')  // current time per metadata
    const diff = d.getTime() - now.getTime()
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)))
}

// Animated counting number
function CountUp({ target, suffix = '' }: { target: number; suffix?: string }) {
    const [val, setVal] = useState(0)
    const ref = useRef<number | null>(null)
    useEffect(() => {
        const dur = 900
        const start = performance.now()
        const tick = (now: number) => {
            const t = Math.min((now - start) / dur, 1)
            const eased = 1 - Math.pow(1 - t, 3)
            setVal(Math.round(eased * target))
            if (t < 1) ref.current = requestAnimationFrame(tick)
        }
        ref.current = requestAnimationFrame(tick)
        return () => { if (ref.current) cancelAnimationFrame(ref.current) }
    }, [target])
    return <>{val}{suffix}</>
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface AuditCompletionEstimatorProps {
    auditType: string
    status: string
    startDate?: string   // ISO string — engagement created_at from backend
}

export function AuditCompletionEstimator({ auditType, status, startDate }: AuditCompletionEstimatorProps) {
    const dur = AUDIT_DURATIONS[auditType] ?? DEFAULT_DURATION
    const now = new Date('2026-02-25T18:13:26+05:30')
    const started = startDate ? new Date(startDate) : addWorkingDays(now, -Math.round(dur.arkashri * 0.4))

    const rawProgress = STATUS_PROGRESS[status] ?? 40
    const [progress, setProgress] = useState(rawProgress)
    const [showManual, setShowManual] = useState(false)

    // Derive dates
    const totalDays = dur.arkashri
    const daysElapsed = Math.max(1, Math.round((now.getTime() - started.getTime()) / (1000 * 60 * 60 * 24)))
    const expectedETA = addWorkingDays(started, totalDays)
    const projectedETA = addWorkingDays(started, Math.round((100 / Math.max(progress, 1)) * daysElapsed))
    const remaining = daysUntil(projectedETA)
    const timeSaved = dur.traditional - dur.arkashri

    // Velocity: are we ahead / on track / delayed?
    const expectedProgress = Math.min(100, Math.round((daysElapsed / totalDays) * 100))
    const delta = progress - expectedProgress
    const velocity = delta >= 5 ? 'ahead' : delta >= -10 ? 'on-track' : 'at-risk'

    const velocityConfig = {
        'ahead': { label: 'Ahead of Schedule', color: 'text-emerald-600 bg-emerald-50 border-emerald-200', icon: TrendingUp, dot: 'bg-emerald-500' },
        'on-track': { label: 'On Track', color: 'text-blue-600 bg-blue-50 border-blue-200', icon: CheckCircle2, dot: 'bg-blue-500' },
        'at-risk': { label: 'At Risk', color: 'text-amber-600 bg-amber-50 border-amber-200', icon: AlertTriangle, dot: 'bg-amber-500' },
    }
    const vc = velocityConfig[velocity]

    // Current phase
    let cumPct = 0
    let currentPhase = dur.phases[0]
    for (const ph of dur.phases) {
        cumPct += ph.pct
        if (progress < cumPct) { currentPhase = ph; break }
        currentPhase = ph
    }

    return (
        <div className="mt-6 border-t pt-6">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-0.5">Timeline Intelligence</div>
                    <h3 className="text-lg font-black text-gray-900">Completion Estimator</h3>
                </div>
                <button
                    onClick={() => setShowManual(m => !m)}
                    className="text-xs font-semibold text-[#002776] border border-[#002776]/20 px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors"
                >
                    {showManual ? 'Auto Progress' : 'Adjust Progress'}
                </button>
            </div>

            {/* Velocity badge */}
            <div className={`inline-flex items-center gap-2 text-xs font-bold px-3 py-1.5 rounded-lg border mb-5 ${vc.color}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${vc.dot} ${velocity === 'on-track' ? 'animate-pulse' : ''}`} />
                <vc.icon className="w-3.5 h-3.5" />
                {vc.label}
                {delta !== 0 && <span className="font-normal opacity-70">({Math.abs(delta)}% {delta > 0 ? 'ahead' : 'behind'})</span>}
            </div>

            {/* Manual slider */}
            {showManual && (
                <div className="mb-5 bg-gray-50 rounded-xl border border-gray-100 p-4">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-600">Actual Progress</span>
                        <span className="text-sm font-black text-[#002776]">{progress}%</span>
                    </div>
                    <input
                        type="range" min={0} max={100} value={progress}
                        onChange={e => setProgress(Number(e.target.value))}
                        className="w-full accent-[#002776] h-1.5"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                        <span>0% — Not started</span>
                        <span>100% — Complete</span>
                    </div>
                </div>
            )}

            {/* Key metrics grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                {[
                    {
                        icon: Calendar, label: 'Projected ETA',
                        value: progress >= 100 ? 'Completed' : formatDate(projectedETA),
                        sub: progress >= 100 ? '✓ Done' : `${remaining}d remaining`,
                        color: 'text-[#002776]', bg: 'bg-blue-50',
                    },
                    {
                        icon: Clock, label: 'Days Elapsed',
                        value: daysElapsed,
                        sub: `of ${totalDays}d total (est.)`,
                        color: 'text-gray-700', bg: 'bg-gray-50',
                    },
                    {
                        icon: Zap, label: 'Time Saved',
                        value: `${timeSaved}d`,
                        sub: `vs ${dur.traditional}d manual`,
                        color: 'text-emerald-600', bg: 'bg-emerald-50',
                    },
                    {
                        icon: TrendingUp, label: 'Automation Lift',
                        value: `${Math.round((timeSaved / dur.traditional) * 100)}%`,
                        sub: 'faster than traditional',
                        color: 'text-purple-600', bg: 'bg-purple-50',
                    },
                ].map(m => (
                    <div key={m.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${m.bg}`}>
                            <m.icon className={`w-4 h-4 ${m.color}`} />
                        </div>
                        <div className={`text-xl font-black ${m.color}`}>
                            {typeof m.value === 'number' ? <CountUp target={m.value} /> : m.value}
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">{m.label}</div>
                        <div className="text-xs text-gray-400">{m.sub}</div>
                    </div>
                ))}
            </div>

            {/* Phase timeline */}
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 mb-4">
                <div className="flex items-center justify-between mb-4">
                    <div className="text-sm font-bold text-gray-900">Phase Timeline — {auditType}</div>
                    <div className="text-xs text-gray-400">
                        Start: {formatDate(started)} · ETA: {formatDate(projectedETA)}
                    </div>
                </div>

                {/* Overall progress bar */}
                <div className="mb-5">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Overall Progress</span>
                        <span className="font-bold text-gray-700">{progress}%</span>
                    </div>
                    <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
                        <div
                            className="h-full rounded-full bg-gradient-to-r from-[#002776] to-blue-400 transition-all duration-700"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>

                {/* Individual phase bars */}
                <div className="space-y-3">
                    {dur.phases.map((ph, i) => {
                        // Cumulative start %
                        const phStart = dur.phases.slice(0, i).reduce((a, p) => a + p.pct, 0)
                        const phEnd = phStart + ph.pct
                        const fill = Math.min(100, Math.max(0, ((progress - phStart) / ph.pct) * 100))
                        const isCurrent = progress >= phStart && progress < phEnd
                        const isDone = progress >= phEnd

                        return (
                            <div key={ph.name} className={`flex items-center gap-3 ${isCurrent ? 'opacity-100' : isDone ? 'opacity-70' : 'opacity-40'}`}>
                                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-black
                                    ${isDone ? 'bg-green-500 text-white' : isCurrent ? 'bg-[#002776] text-white animate-pulse' : 'bg-gray-100 text-gray-400'}`}>
                                    {isDone ? '✓' : i + 1}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between mb-0.5">
                                        <span className="text-xs font-semibold text-gray-700 truncate">{ph.name}</span>
                                        <span className="text-xs text-gray-400 ml-2 flex-shrink-0">{ph.days}d</span>
                                    </div>
                                    <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full transition-all duration-700 ${isDone ? 'bg-green-400' : 'bg-[#002776]'}`}
                                            style={{ width: `${fill}%` }}
                                        />
                                    </div>
                                </div>
                                {isCurrent && (
                                    <span className="text-xs font-semibold text-[#002776] bg-blue-50 px-2 py-0.5 rounded-full flex-shrink-0">
                                        Active
                                    </span>
                                )}
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Arkashri speed-up callout */}
            <div className="flex items-start gap-3 bg-gradient-to-r from-[#001a54]/5 to-blue-50 border border-blue-100 rounded-xl p-4">
                <Zap className="w-4 h-4 text-[#002776] flex-shrink-0 mt-0.5" />
                <div>
                    <div className="text-xs font-bold text-[#002776] mb-0.5">Arkashri Automation Speed-Up</div>
                    <p className="text-xs text-gray-600 leading-relaxed">
                        Traditional <strong>{auditType}</strong> takes <strong>{dur.traditional} calendar days</strong>.
                        Arkashri's 93% automation engine completes it in <strong className="text-emerald-600">{dur.arkashri} days</strong>,
                        saving <strong>{timeSaved} days</strong> ({Math.round((timeSaved / dur.traditional) * 100)}% faster).
                        {' '}Current active phase: <strong>{currentPhase.name}</strong>.
                    </p>
                </div>
            </div>
        </div>
    )
}
