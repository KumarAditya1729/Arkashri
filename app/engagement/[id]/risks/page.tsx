'use client'

import { useState, useEffect, use } from 'react'
import { Plus, AlertTriangle, ShieldAlert, Filter, ArrowUpDown, ChevronRight, CheckCircle2, Loader2 } from 'lucide-react'
import { getRisks, createRisk, RiskResponse, RiskLikelihood, RiskImpact, RiskStatus } from '@/lib/api'
import { getUuid } from '@/lib/engagementRegistry'

// ─── Local seed data (shown when backend unreachable) ─────────────────────────

const SEED_RISKS: RiskResponse[] = []

// ─── Style maps ───────────────────────────────────────────────────────────────

const likelihoodColor: Record<RiskLikelihood, string> = { High: 'bg-red-100 text-red-700', Medium: 'bg-orange-100 text-orange-700', Low: 'bg-green-100 text-green-700' }
const impactColor: Record<RiskImpact, string> = { Critical: 'bg-red-600 text-white', High: 'bg-orange-500 text-white', Medium: 'bg-yellow-400 text-gray-900', Low: 'bg-green-400 text-white' }
const statusConfig: Record<RiskStatus, { color: string; dot: string }> = {
    Open: { color: 'text-red-600 bg-red-50', dot: 'bg-red-500' },
    'In Review': { color: 'text-blue-600 bg-blue-50', dot: 'bg-blue-500' },
    Mitigated: { color: 'text-green-600 bg-green-50', dot: 'bg-green-500' },
    Accepted: { color: 'text-gray-600 bg-gray-100', dot: 'bg-gray-400' },
}

function RiskScoreBar({ score }: { score: number }) {
    const color = score >= 80 ? 'bg-red-500' : score >= 60 ? 'bg-orange-400' : score >= 40 ? 'bg-yellow-400' : 'bg-green-400'
    return (
        <div className="flex items-center gap-2">
            <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
            </div>
            <span className="text-sm font-bold text-gray-700">{score}</span>
        </div>
    )
}

export default function RisksPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params)
    const uuid = getUuid(id)

    const [risks, setRisks] = useState<RiskResponse[]>(SEED_RISKS)
    const [isLive, setIsLive] = useState(false)
    const [loading, setLoading] = useState(false)
    const [saving, setSaving] = useState(false)
    const [filter, setFilter] = useState<RiskStatus | 'All'>('All')
    const [showAdd, setShowAdd] = useState(false)
    const [newRisk, setNewRisk] = useState({ title: '', area: '', likelihood: 'Medium' as RiskLikelihood, impact: 'Medium' as RiskImpact, owner: '' })

    useEffect(() => {
        if (!uuid) return
        setLoading(true)
        getRisks(uuid).then(data => {
            if (data.length > 0) {
                setRisks(data)
                setIsLive(true)
            }
        }).finally(() => setLoading(false))
    }, [uuid])

    const filtered = filter === 'All' ? risks : risks.filter(r => r.risk_status === filter)

    const handleAdd = async () => {
        if (!newRisk.title.trim()) return
        setSaving(true)
        if (uuid) {
            try {
                const created = await createRisk(uuid, {
                    title: newRisk.title,
                    area: newRisk.area || 'General',
                    likelihood: newRisk.likelihood,
                    impact: newRisk.impact,
                    owner: newRisk.owner || 'Unassigned',
                })
                setRisks(r => [created, ...r])
                setIsLive(true)
            } catch {
                // Fallback: add locally
                const score = ({ High: 3, Medium: 2, Low: 1 }[newRisk.likelihood]) * ({ Critical: 4, High: 3, Medium: 2, Low: 1 }[newRisk.impact]) * 8
                const local: RiskResponse = {
                    id: crypto.randomUUID(), engagement_id: '', risk_ref: `RSK-${String(risks.length + 1).padStart(3, '0')}`,
                    title: newRisk.title, area: newRisk.area || 'General', likelihood: newRisk.likelihood, impact: newRisk.impact,
                    risk_score: Math.min(score, 99), owner: newRisk.owner || 'Unassigned', control_ref: null, risk_status: 'Open', created_at: '', updated_at: '',
                }
                setRisks(r => [local, ...r])
            }
        }
        setNewRisk({ title: '', area: '', likelihood: 'Medium', impact: 'Medium', owner: '' })
        setShowAdd(false)
        setSaving(false)
    }

    return (
        <>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <h1 className="text-xl font-bold text-[#002776] tracking-tight">Phase 2: Risk Register</h1>
                        {isLive ? (
                            <span className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />LIVE
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />LOCAL
                            </span>
                        )}
                        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
                    </div>
                    <p className="text-gray-500 text-xs text-balance">Identify, assess, and track audit risks for ENG-{id}.</p>
                </div>
                <button onClick={() => setShowAdd(!showAdd)} className="flex items-center gap-2 bg-[#002776] text-white text-xs font-semibold px-4 py-1.5 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm">
                    <Plus className="w-3.5 h-3.5" /> Add Risk
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {[
                    { label: 'Total Risks', value: risks.length, icon: ShieldAlert, color: 'text-[#002776]' },
                    { label: 'Open', value: risks.filter(r => r.risk_status === 'Open').length, icon: AlertTriangle, color: 'text-red-500' },
                    { label: 'Critical Impact', value: risks.filter(r => r.impact === 'Critical').length, icon: AlertTriangle, color: 'text-orange-500' },
                    { label: 'Mitigated', value: risks.filter(r => r.risk_status === 'Mitigated').length, icon: CheckCircle2, color: 'text-green-500' },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
                        <s.icon className={`w-8 h-8 ${s.color} flex-shrink-0`} />
                        <div>
                            <div className="text-2xl font-black text-gray-900">{s.value}</div>
                            <div className="text-xs text-gray-500">{s.label}</div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Add Risk Form */}
            {showAdd && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-5">
                    <h3 className="font-semibold text-gray-900 mb-4">Add New Risk</h3>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="col-span-2">
                            <label className="text-xs font-semibold text-gray-600 mb-1 block">Risk Title *</label>
                            <input value={newRisk.title} onChange={e => setNewRisk(n => ({ ...n, title: e.target.value }))} placeholder="Describe the risk…" className="w-full h-9 px-3 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30" />
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1 block">Audit Area</label>
                            <input value={newRisk.area} onChange={e => setNewRisk(n => ({ ...n, area: e.target.value }))} placeholder="e.g. Revenue" className="w-full h-9 px-3 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30" />
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1 block">Owner</label>
                            <input value={newRisk.owner} onChange={e => setNewRisk(n => ({ ...n, owner: e.target.value }))} placeholder="Auditor name" className="w-full h-9 px-3 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30" />
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1 block">Likelihood</label>
                            <select value={newRisk.likelihood} onChange={e => setNewRisk(n => ({ ...n, likelihood: e.target.value as RiskLikelihood }))} className="w-full h-9 px-3 rounded-lg border border-gray-200 text-sm focus:outline-none">
                                {['High', 'Medium', 'Low'].map(v => <option key={v}>{v}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1 block">Impact</label>
                            <select value={newRisk.impact} onChange={e => setNewRisk(n => ({ ...n, impact: e.target.value as RiskImpact }))} className="w-full h-9 px-3 rounded-lg border border-gray-200 text-sm focus:outline-none">
                                {['Critical', 'High', 'Medium', 'Low'].map(v => <option key={v}>{v}</option>)}
                            </select>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={handleAdd} disabled={saving} className="flex items-center gap-2 bg-[#002776] text-white text-xs font-semibold px-4 py-2 rounded-lg hover:bg-[#001a54] disabled:opacity-50">
                            {saving ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Saving…</> : 'Add to Register'}
                        </button>
                        <button onClick={() => setShowAdd(false)} className="text-gray-500 text-sm font-semibold px-4 py-2 rounded-lg hover:bg-gray-100">Cancel</button>
                    </div>
                </div>
            )}

            {/* Filter */}
            <div className="flex items-center gap-2 mb-4">
                <Filter className="w-4 h-4 text-gray-400" />
                {(['All', 'Open', 'In Review', 'Mitigated', 'Accepted'] as const).map(f => (
                    <button key={f} onClick={() => setFilter(f)} className={`text-xs font-semibold px-3 py-1 rounded-full border transition-all ${filter === f ? 'bg-[#002776] text-white border-[#002776]' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}>{f}</button>
                ))}
                <span className="ml-auto text-[10px] text-gray-400 flex items-center gap-1 uppercase font-bold tracking-wider"><ArrowUpDown className="w-3 h-3" />Sorted by risk score</span>
            </div>

            {/* Risk Table */}
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 text-[10px] text-gray-500 uppercase tracking-wider">
                        <tr>
                            <th className="text-left px-5 py-3">ID</th>
                            <th className="text-left px-5 py-3">Risk</th>
                            <th className="text-left px-5 py-3">Area</th>
                            <th className="text-center px-5 py-3">Likelihood</th>
                            <th className="text-center px-5 py-3">Impact</th>
                            <th className="text-left px-5 py-3">Score</th>
                            <th className="text-left px-5 py-3">Status</th>
                            <th className="text-left px-5 py-3">Owner</th>
                            <th className="px-5 py-3" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                        {filtered.sort((a, b) => b.risk_score - a.risk_score).map(risk => {
                            const s = statusConfig[risk.risk_status]
                            return (
                                <tr key={risk.id} className="hover:bg-gray-50 transition-colors cursor-pointer">
                                    <td className="px-5 py-3.5 font-mono text-[10px] text-gray-400">{risk.risk_ref}</td>
                                    <td className="px-5 py-3.5 font-medium text-gray-900 max-w-xs text-xs">{risk.title}</td>
                                    <td className="px-5 py-3.5 text-gray-500 text-xs">{risk.area}</td>
                                    <td className="px-5 py-3.5 text-center">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${likelihoodColor[risk.likelihood]}`}>{risk.likelihood}</span>
                                    </td>
                                    <td className="px-5 py-3.5 text-center">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${impactColor[risk.impact]}`}>{risk.impact}</span>
                                    </td>
                                    <td className="px-5 py-3.5"><RiskScoreBar score={risk.risk_score} /></td>
                                    <td className="px-5 py-3.5">
                                        <span className={`inline-flex items-center gap-1.5 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${s.color}`}>
                                            <span className={`w-1 h-1 rounded-full ${s.dot}`} />
                                            {risk.risk_status}
                                        </span>
                                    </td>
                                    <td className="px-5 py-3.5 text-gray-500 text-[10px] font-semibold">{risk.owner}</td>
                                    <td className="px-5 py-3.5"><ChevronRight className="w-4 h-4 text-gray-300" /></td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </>
    )
}
