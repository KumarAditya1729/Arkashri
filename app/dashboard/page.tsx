'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { AutomationScoreWidget } from '@/components/audit/AutomationScoreWidget'
import Link from 'next/link'
import { ArrowRight, Activity, Users, FileWarning, TrendingUp, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getAutomationScore, AutomationScoreResponse, getEngagements, EngagementResponse } from '@/lib/api'

// Dynamically fetched
const statusColors: Record<string, string> = {
    'In Progress': 'bg-blue-100 text-blue-800',
    'Planning': 'bg-amber-100 text-amber-800',
    'Review': 'bg-purple-100 text-purple-800',
    'Completed': 'bg-green-100 text-green-700',
    'Not Started': 'bg-gray-100 text-gray-600',
}

const riskDot: Record<string, string> = {
    Critical: 'bg-red-500',
    High: 'bg-orange-400',
    Medium: 'bg-yellow-400',
    Low: 'bg-green-400',
}

const auditIcons: Record<string, string> = {
    'Forensic Audit': '🔍',
    'Financial Audit': '💰',
    'ESG Audit': '🌿',
    'Internal Audit': '🏛️',
    'External Audit': '🔬',
    'Statutory Audit': '📜',
    'Tax Audit': '🧾',
    'Compliance Audit': '✅',
    'Operational Audit': '⚙️',
    'IT Audit': '💻',
    'Payroll Audit': '👥',
    'Performance Audit': '📈',
    'Quality Audit': '🎯',
    'Environmental Audit': '♻️',
}

export default function Dashboard() {
    const [ENGAGEMENTS, setEngagements] = useState<any[]>([])

    const inProgress = ENGAGEMENTS.filter(e => e.status === 'In Progress').length
    const critical = ENGAGEMENTS.filter(e => e.risk === 'Critical').length
    const pending = ENGAGEMENTS.filter(e => e.status === 'Planning' || e.status === 'Not Started').length

    const [automationData, setAutomationData] = useState<AutomationScoreResponse | null>(null)
    const [scoreLoading, setScoreLoading] = useState(true)
    const [isLiveScore, setIsLiveScore] = useState(false)

    useEffect(() => {
        getAutomationScore().then(data => {
            if (data) {
                setAutomationData(data)
                setIsLiveScore(data.dimensions.some(d => d.total > 0))
            }
        }).finally(() => setScoreLoading(false))

        getEngagements().then(data => {
            // Map EngagementResponse to local format for UI
            setEngagements(data.map(d => ({
                id: d.id,
                type: d.engagement_type,
                client: d.client_name,
                status: d.status === 'FIELD_WORK' ? 'In Progress' :
                    d.status === 'REVIEW' ? 'Review' :
                        d.status === 'COMPLETED' || d.status === 'SEALED' ? 'Completed' : 'Planning',
                risk: 'Medium'
            })))
        })
    }, [])

    return (
        <AuditShell>
            <div className="mb-6">
                <h1 className="text-3xl font-black text-[#002776] mb-1 tracking-tight">Operator Dashboard</h1>
                <p className="text-gray-500 text-sm">Universal Audit Command Surface — {ENGAGEMENTS.length} active mandates across all audit types</p>
            </div>

            {/* Top grid: KPI cards + Automation Score Widget */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                {/* KPI cards */}
                {[
                    { label: 'Active Mandates', value: ENGAGEMENTS.length, sub: 'Assigned engagements', icon: Activity, color: 'text-[#002776]', bg: 'bg-blue-50' },
                    { label: 'In Progress', value: inProgress, sub: 'Actively running', icon: TrendingUp, color: 'text-blue-600', bg: 'bg-blue-50' },
                    { label: 'Pending Review', value: pending, sub: 'Awaiting action', icon: Users, color: 'text-amber-500', bg: 'bg-amber-50' },
                    { label: 'Critical Risk', value: critical, sub: 'Require escalation', icon: FileWarning, color: 'text-red-600', bg: 'bg-red-50' },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${s.bg}`}>
                            <s.icon className={`w-5 h-5 ${s.color}`} />
                        </div>
                        <div>
                            <div className={`text-2xl font-black ${s.color}`}>{s.value}</div>
                            <div className="text-xs text-gray-500 leading-tight">{s.label}</div>
                            <div className="text-xs text-gray-300">{s.sub}</div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Automation Score Widget — full width */}
            <div className="mb-8">
                {scoreLoading ? (
                    <div className="bg-gradient-to-br from-[#001a54] via-[#002776] to-[#0040a0] rounded-2xl p-8 flex items-center justify-center gap-3 text-white min-h-[140px]">
                        <Loader2 className="w-5 h-5 animate-spin text-blue-300" />
                        <span className="text-blue-200 text-sm">Loading automation score…</span>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 relative">
                        {!automationData && (
                            <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] rounded-2xl z-10 flex items-center justify-center">
                                <div className="bg-white/90 backdrop-blur-md px-4 py-2 rounded-lg border border-red-100 shadow-xl flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                    <span className="text-[10px] font-black text-red-600 uppercase tracking-widest">Decision Engine Offline — Showing Stale Model</span>
                                </div>
                            </div>
                        )}
                        <AutomationScoreWidget
                            score={automationData?.overall_score ?? 93.4}
                            grade={automationData?.grade ?? 'A'}
                            insight={automationData?.insight ?? 'Local baseline loaded. Connect to production to sync live decision deltas.'}
                            dimensions={automationData?.dimensions ?? [
                                { label: 'Decision Engine Coverage', score: 96.2, weight: 0.35, automated: 0, total: 0, description: '' },
                                { label: 'Audit Step Completion', score: 91.4, weight: 0.25, automated: 0, total: 0, description: '' },
                                { label: 'Approval Auto-Clearance', score: 88.7, weight: 0.20, automated: 0, total: 0, description: '' },
                                { label: 'Exception Auto-Triage', score: 90.3, weight: 0.12, automated: 0, total: 0, description: '' },
                                { label: 'Risk Quantification', score: 99.1, weight: 0.08, automated: 0, total: 0, description: '' },
                            ]}
                            isLive={isLiveScore}
                        />
                    </div>
                )}
            </div>

            {/* All engagements */}
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-[#002776]">All Engagements</h2>
                <Link href="/engagement-overview" className="text-sm font-semibold text-[#002776] hover:underline flex items-center gap-1">
                    View all <ArrowRight className="w-3.5 h-3.5" />
                </Link>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {ENGAGEMENTS.map((e) => (
                    <Link href={`/engagement/${e.id}`} key={e.id} className="block group">
                        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 hover:border-[#002776] hover:shadow-md transition-all h-full cursor-pointer">
                            <div className="flex items-start justify-between mb-3">
                                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${statusColors[e.status]}`}>{e.status}</span>
                                <ArrowRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-[#002776] transition-colors" />
                            </div>
                            <div className="flex items-center gap-1.5 mb-1">
                                <span className="text-lg">{auditIcons[e.type]}</span>
                                <h3 className="font-bold text-gray-900 text-sm leading-tight">{e.type}</h3>
                            </div>
                            <p className="text-gray-400 text-xs mb-3">{e.client}</p>
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-mono text-gray-300">ENG-{e.id}</span>
                                <span className="flex items-center gap-1 text-xs text-gray-500">
                                    <span className={`w-1.5 h-1.5 rounded-full ${riskDot[e.risk]}`} />
                                    {e.risk}
                                </span>
                            </div>
                        </div>
                    </Link>
                ))}
            </div>
        </AuditShell>
    )
}
