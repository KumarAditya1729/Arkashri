'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import Link from 'next/link'
import { ArrowRight, Search, Filter, Loader2, Calendar } from 'lucide-react'
import { useState, useEffect } from 'react'
import { getEngagements } from '@/lib/api'

type AuditStatus = 'In Progress' | 'Planning' | 'Review' | 'Completed' | 'Not Started'

// Data will be fetched from the backend
const statusColors: Record<AuditStatus, string> = {
    'In Progress': 'bg-blue-100 text-blue-800 border-blue-200',
    'Planning': 'bg-amber-100 text-amber-800 border-amber-200',
    'Review': 'bg-purple-100 text-purple-800 border-purple-200',
    'Completed': 'bg-green-100 text-green-700 border-green-200',
    'Not Started': 'bg-gray-100 text-gray-600 border-gray-200',
}

const riskColors: Record<string, string> = {
    Critical: 'text-red-600',
    High: 'text-orange-500',
    Medium: 'text-yellow-600',
    Low: 'text-green-600',
}

const auditTypeIcons: Record<string, string> = {
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

export default function EngagementOverviewPage() {
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState<AuditStatus | 'All'>('All')
    const [ALL_ENGAGEMENTS, setAllEngagements] = useState<{ id: string; type: string; client: string; status: AuditStatus; risk: string; period: string }[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        getEngagements().then(data => {
            setAllEngagements(data.map(d => ({
                id: d.id,
                type: d.engagement_type,
                client: d.client_name,
                status: d.status === 'FIELD_WORK' ? 'In Progress' :
                    d.status === 'REVIEW' ? 'Review' :
                        d.status === 'COMPLETED' || d.status === 'SEALED' ? 'Completed' : 'Planning',
                risk: 'Medium',
                period: 'Current'
            })))
        }).finally(() => setLoading(false))
    }, [])

    const filtered = ALL_ENGAGEMENTS
        .filter(e => statusFilter === 'All' || e.status === statusFilter)
        .filter(e =>
            e.type.toLowerCase().includes(search.toLowerCase()) ||
            e.client.toLowerCase().includes(search.toLowerCase()) ||
            e.id.includes(search)
        )

    const byStatus = (s: AuditStatus) => ALL_ENGAGEMENTS.filter(e => e.status === s).length

    return (
        <AuditShell>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Universal Audit</div>
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">Engagement Overview</h1>
                    <p className="text-gray-500 mt-1 text-sm">All 14 audit types — {ALL_ENGAGEMENTS.length} active engagements across your mandate portfolio.</p>
                </div>
            </div>

            {/* Status summary pills */}
            <div className="flex gap-3 mb-6 flex-wrap">
                {([
                    { label: 'All', count: ALL_ENGAGEMENTS.length },
                    { label: 'In Progress', count: byStatus('In Progress') },
                    { label: 'Planning', count: byStatus('Planning') },
                    { label: 'Review', count: byStatus('Review') },
                    { label: 'Completed', count: byStatus('Completed') },
                    { label: 'Not Started', count: byStatus('Not Started') },
                ] as const).map(({ label, count }) => (
                    <button
                        key={label}
                        onClick={() => setStatusFilter(label as AuditStatus | 'All')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-semibold transition-all ${statusFilter === label ? 'bg-[#002776] text-white border-[#002776] shadow-md' : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'}`}
                    >
                        {label}
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${statusFilter === label ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-500'}`}>{count}</span>
                    </button>
                ))}
            </div>

            {/* Search */}
            <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="Search by audit type, client, or engagement ID…"
                    className="w-full h-10 pl-10 pr-4 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 bg-white"
                />
            </div>

            {/* Engagement grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filtered.map(e => (
                    <Link href={`/engagement/${e.id}`} key={e.id} className="block group">
                        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 hover:border-[#002776] hover:shadow-md transition-all h-full cursor-pointer">
                            <div className="flex items-start justify-between mb-3">
                                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${statusColors[e.status]}`}>{e.status}</span>
                                <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-[#002776] transition-colors" />
                            </div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-xl">{auditTypeIcons[e.type]}</span>
                                <h3 className="font-bold text-gray-900 text-base leading-tight">{e.type}</h3>
                            </div>
                            <p className="text-gray-500 text-sm mb-3">{e.client}</p>
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-mono text-gray-400">ENG-{e.id} · {e.period}</span>
                                <span className={`text-xs font-bold ${riskColors[e.risk]}`}>{e.risk} Risk</span>
                            </div>
                        </div>
                    </Link>
                ))}
            </div>

            {loading && (
                <div className="flex justify-center items-center py-16">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                </div>
            )}
            {!loading && filtered.length === 0 && (
                <div className="text-center py-16 text-gray-400">
                    <Filter className="w-8 h-8 mx-auto mb-3 opacity-30" />
                    <p className="font-medium">No engagements match your filter or no engagements exist.</p>
                </div>
            )}
        </AuditShell>
    )
}
