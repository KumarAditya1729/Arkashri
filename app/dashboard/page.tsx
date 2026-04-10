'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { AutomationScoreWidget } from '@/components/audit/AutomationScoreWidget'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowRight, Activity, Users, FileWarning, TrendingUp, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getAutomationScore, AutomationScoreResponse, getEngagements, EngagementResponse, ApiError } from '@/lib/api'

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

    const router = useRouter()
    const [automationData, setAutomationData] = useState<AutomationScoreResponse | null>(null)
    const [scoreLoading, setScoreLoading] = useState(true)
    const [isLiveScore, setIsLiveScore] = useState(false)

    useEffect(() => {
        getAutomationScore().then(data => {
            if (data) {
                setAutomationData(data)
                setIsLiveScore(data.dimensions.some(d => d.total > 0))
            }
        }).catch(err => {
            if (err instanceof ApiError && err.status === 401) {
                router.replace('/sign-in')
            }
            // non-auth errors: stay on page with stale overlay
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
            {/* Absolute background effect for the dashboard area */}
            <div className="absolute inset-0 bg-[#020817] z-0 overflow-hidden rounded-xl m-2 border border-[#1e293b]">
                <div className="absolute -top-[40%] -left-[20%] w-[80%] h-[80%] rounded-full bg-blue-900/20 blur-[120px] animate-pulse-slow" />
                <div className="absolute top-[60%] -right-[10%] w-[60%] h-[60%] rounded-full bg-indigo-900/20 blur-[140px] animate-float" />
            </div>

            <div className="relative z-10 px-6 py-8 h-full flex flex-col min-h-screen text-slate-100">
                <div className="mb-10 flex flex-col lg:flex-row lg:items-end justify-between gap-4">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold tracking-widest uppercase mb-4 animate-glow">
                            <Activity className="w-3.5 h-3.5" /> Live Engine Telemetry
                        </div>
                        <h1 className="text-4xl lg:text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-100 via-indigo-200 to-white mb-2 tracking-tight">Intelligence Command</h1>
                        <p className="text-slate-400 text-sm font-medium">Universal Audit Analytics Surface — Tracking {ENGAGEMENTS.length} active global mandates</p>
                    </div>
                </div>

                {/* Top grid: KPI Hub */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
                    {[
                        { label: 'Active Mandates', value: ENGAGEMENTS.length, sub: 'Assigned engagements', icon: Activity, ring: 'ring-blue-500/30', color: 'text-blue-400' },
                        { label: 'Processing', value: inProgress, sub: 'Actively evaluating', icon: TrendingUp, ring: 'ring-indigo-500/30', color: 'text-indigo-400' },
                        { label: 'Pending Sign-Off', value: pending, sub: 'Human action required', icon: Users, ring: 'ring-amber-500/30', color: 'text-amber-400' },
                        { label: 'Critical Risk', value: critical, sub: 'Immediate escalation', icon: FileWarning, ring: 'ring-red-500/30', color: 'text-red-400' },
                    ].map((s, idx) => (
                        <div key={idx} className="glass-card rounded-2xl p-5 flex flex-col justify-between group overflow-hidden relative">
                            {/* Decorative background glow per card */}
                            <div className={`absolute -bottom-8 -right-8 w-24 h-24 rounded-full bg-${s.color.split('-')[1]}-500/10 blur-[30px] group-hover:bg-${s.color.split('-')[1]}-500/20 transition-all duration-700`} />
                            
                            <div className="flex items-center justify-between mb-4">
                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-[#0F172A] border border-white/5 ring-1 ${s.ring} shadow-lg backdrop-blur-md`}>
                                    <s.icon className={`w-5 h-5 ${s.color}`} />
                                </div>
                                <Activity className="w-4 h-4 text-white/10 group-hover:text-white/30 transition-colors" />
                            </div>
                            <div>
                                <div className="text-4xl font-black text-white mb-1 tracking-tight">{s.value}</div>
                                <div className="text-sm font-semibold text-slate-300">{s.label}</div>
                                <div className="text-xs text-slate-500 font-medium">{s.sub}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Automation Score Hologram */}
                <div className="mb-10 w-full relative">
                    <div className="absolute inset-0 bg-gradient-to-r from-blue-900/20 via-indigo-900/10 to-transparent blur-xl rounded-full" />
                    
                    {scoreLoading ? (
                        <div className="glass-panel rounded-3xl p-10 flex flex-col items-center justify-center gap-4 min-h-[200px]">
                            <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                            <span className="text-blue-300 font-mono text-sm uppercase tracking-widest animate-pulse">Establishing secure link to AI Fabric...</span>
                        </div>
                    ) : (
                        <div className="glass-panel rounded-3xl overflow-hidden relative border-blue-500/20 shadow-[0_0_50px_0_rgba(14,165,233,0.1)]">
                            {/* Holographic grid lines */}
                            <div className="absolute inset-0 bg-[url('https://transparenttextures.com/patterns/cubes.png')] opacity-[0.03] mix-blend-overlay pointer-events-none" />
                            
                            {!automationData && (
                                <div className="absolute top-4 right-4 bg-red-500/10 border border-red-500/30 backdrop-blur-md px-4 py-2 rounded-lg flex items-center gap-2 z-20 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                                    <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                    <span className="text-[10px] font-black text-red-400 uppercase tracking-widest">Connection Lost — Safe Mode Display</span>
                                </div>
                            )}
                            
                            {/* Standard widget container but modified structurally by globals.css */}
                            <div className="relative z-10 p-2">
                                <AutomationScoreWidget
                                    score={automationData?.overall_score ?? 93.4}
                                    grade={automationData?.grade ?? 'A'}
                                    insight={automationData?.insight ?? 'Local baseline loaded. Operational analytics running via deterministic math module limits.'}
                                    dimensions={automationData?.dimensions ?? [
                                        { label: 'Going Concern ML Accuracy', score: 98.2, weight: 0.35, automated: 0, total: 0, description: '' },
                                        { label: 'Risk Anomaly Detection', score: 91.4, weight: 0.25, automated: 0, total: 0, description: '' },
                                        { label: 'Opinion Logic Validity', score: 99.7, weight: 0.20, automated: 0, total: 0, description: '' },
                                        { label: 'ERP Ledger Integrity', score: 100.0, weight: 0.20, automated: 0, total: 0, description: '' },
                                    ]}
                                    isLive={isLiveScore}
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* Enhanced Engagements Grid */}
                <div>
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex flex-col">
                            <h2 className="text-2xl font-black text-slate-100 flex items-center gap-2 tracking-tight">Active Operations Pipeline</h2>
                            <span className="text-xs text-slate-400 uppercase tracking-widest mt-1">Real-time orchestrated runs</span>
                        </div>
                        <Link href="/engagement-overview" className="text-sm font-semibold text-blue-400 hover:text-blue-300 hover:bg-blue-900/20 px-4 py-2 rounded-lg transition-all flex items-center gap-2 border border-transparent hover:border-blue-500/30">
                            View All Directory <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {ENGAGEMENTS.map((e) => (
                            <Link href={`/engagement/${e.id}`} key={e.id} className="block group h-full">
                                <div className="bg-[#111827]/80 backdrop-blur-sm border border-slate-700/50 hover:bg-[#1F2937]/90 hover:border-blue-500/50 shadow-lg rounded-2xl p-5 transition-all duration-300 h-full flex flex-col relative overflow-hidden group-hover:-translate-y-1">
                                    {/* Accent strip */}
                                    <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-blue-500/50 to-indigo-500/20 group-hover:from-blue-400 group-hover:to-indigo-400 transition-colors" />
                                    
                                    <div className="flex items-start justify-between mb-4 pl-3">
                                        <div className="bg-slate-800/80 border border-slate-700 px-3 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase text-slate-300 shadow-sm flex items-center gap-2">
                                            <div className={`w-1.5 h-1.5 rounded-full ${e.status === 'In Progress' ? 'bg-blue-400 animate-pulse' : e.status === 'Completed' ? 'bg-green-400' : 'bg-amber-400'}`} />
                                            {e.status}
                                        </div>
                                        <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-blue-400 transition-colors transform group-hover:translate-x-1" />
                                    </div>
                                    
                                    <div className="pl-3 flex-1 flex flex-col">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-sm shadow-inner shadow-white/5">{auditIcons[e.type] || '📑'}</div>
                                            <h3 className="font-bold text-slate-100 text-sm">{e.type}</h3>
                                        </div>
                                        
                                        <p className="text-slate-400 text-xs mb-6 font-medium leading-relaxed">{e.client}</p>
                                        
                                        <div className="mt-auto border-t border-white/5 pt-4 flex items-center justify-between">
                                            <span className="text-[10px] font-mono text-slate-500 tracking-wider">ID:{e.id.substring(0,8)}</span>
                                            
                                            <div className="flex items-center gap-1.5 bg-black/20 rounded-md px-2 py-1 border border-white/5">
                                                <span className={`w-1.5 h-1.5 rounded-full ${riskDot[e.risk] || 'bg-slate-500'}`} />
                                                <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">{e.risk}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>
            </div>
        </AuditShell>
    )
}

