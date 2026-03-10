'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { useState, useEffect } from 'react'
import { ExternalLink, BookOpen, Bell, CheckCircle2, Clock, AlertTriangle, Filter, Loader2 } from 'lucide-react'
import { getRegulatoryDocuments, promoteRegulatoryDoc, RegulatoryDoc } from '@/lib/api'

const issuerColor: Record<string, string> = {
    ICAI: 'bg-blue-100 text-blue-800',
    SEBI: 'bg-purple-100 text-purple-800',
    MCA: 'bg-green-100 text-green-800',
    RBI: 'bg-teal-100 text-teal-800',
    IASB: 'bg-indigo-100 text-indigo-800',
    PCAOB: 'bg-orange-100 text-orange-800',
}
const impactColor: Record<string, string> = { High: 'text-red-600 bg-red-50', Medium: 'text-orange-600 bg-orange-50', Low: 'text-gray-500 bg-gray-100' }

// ─── Local seed (shown when DB has no regulatory documents) ───────────────────

interface LocalDoc {
    id: string | number
    title: string
    issuer: string
    effectiveDate?: string
    postedDate?: string
    impact: string
    summary: string
    source_url?: string | null
    is_promoted: boolean
    isLocal?: boolean
}

const SEED_DOCS: LocalDoc[] = []

function liveToLocal(d: RegulatoryDoc): LocalDoc {
    // Try to parse issuer from title if not in issuer field
    const knownIssuers = ['ICAI', 'SEBI', 'MCA', 'RBI', 'IASB', 'PCAOB']
    const detectedIssuer = knownIssuers.find(i => d.title?.toUpperCase().includes(i) || d.issuer?.toUpperCase().includes(i)) ?? d.issuer ?? 'ICAI'
    // Heuristic impact from content keywords  
    const impact = d.content?.toLowerCase().includes('mandatory') || d.content?.toLowerCase().includes('strict') ? 'High' : d.content?.toLowerCase().includes('recommend') ? 'Medium' : 'Low'
    return {
        id: d.id,
        title: d.title,
        issuer: detectedIssuer,
        postedDate: d.ingested_at?.slice(0, 10),
        impact,
        summary: d.content?.slice(0, 300) ?? 'Regulatory document ingested from official source.',
        source_url: d.source_url,
        is_promoted: d.is_promoted,
    }
}

export default function RegulatoryUpdatesPage() {
    const [docs, setDocs] = useState<LocalDoc[]>(SEED_DOCS)
    const [isLive, setIsLive] = useState(false)
    const [loading, setLoading] = useState(false)
    const [promoting, setPromoting] = useState<string | number | null>(null)
    const [filterIssuer, setFilterIssuer] = useState<string>('All')
    const [filterImpact, setFilterImpact] = useState<string>('All')
    const [expanded, setExpanded] = useState<string | number | null>('loc-1')

    useEffect(() => {
        setLoading(true)
        getRegulatoryDocuments('IN').then(data => {
            if (data.length > 0) {
                setDocs(data.map(liveToLocal))
                setIsLive(true)
                setExpanded(data[0].id)
            }
        }).finally(() => setLoading(false))
    }, [])

    const acknowledge = async (doc: LocalDoc) => {
        if (!doc.isLocal && typeof doc.id === 'number') {
            setPromoting(doc.id)
            try { await promoteRegulatoryDoc(doc.id) } catch { /* fallback */ }
            setPromoting(null)
        }
        setDocs(ds => ds.map(d => d.id === doc.id ? { ...d, is_promoted: true } : d))
    }

    const filtered = docs
        .filter(d => filterIssuer === 'All' || d.issuer === filterIssuer)
        .filter(d => filterImpact === 'All' || d.impact === filterImpact)

    const unacknowledged = docs.filter(d => !d.is_promoted).length

    return (
        <AuditShell>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Audit Workflow</div>
                    <div className="flex items-center gap-2 mb-1">
                        <h1 className="text-3xl font-black text-[#002776] tracking-tight">Regulatory Updates</h1>
                        {isLive ? (
                            <span className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />LIVE
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />LOCAL
                            </span>
                        )}
                        {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
                    </div>
                    <p className="text-gray-500 mt-1 text-sm">Track relevant regulatory changes, new standards, and impact on active engagements.</p>
                </div>
                {unacknowledged > 0 && (
                    <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm font-semibold px-4 py-2 rounded-lg">
                        <Bell className="w-4 h-4" />{unacknowledged} unreviewed updates
                    </div>
                )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {[
                    { label: 'Total Updates', value: docs.length, icon: BookOpen, color: 'text-[#002776]' },
                    { label: 'High Impact', value: docs.filter(d => d.impact === 'High').length, icon: AlertTriangle, color: 'text-red-500' },
                    { label: 'Acknowledged', value: docs.filter(d => d.is_promoted).length, icon: CheckCircle2, color: 'text-green-500' },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-4">
                        <s.icon className={`w-8 h-8 ${s.color}`} />
                        <div><div className="text-2xl font-black text-gray-900">{s.value}</div><div className="text-xs text-gray-500">{s.label}</div></div>
                    </div>
                ))}
            </div>

            {/* Filters */}
            <div className="flex items-center gap-3 mb-5 flex-wrap">
                <Filter className="w-4 h-4 text-gray-400" />
                <div className="flex gap-1">
                    {['All', 'ICAI', 'SEBI', 'MCA', 'RBI', 'IASB', 'PCAOB'].map(f => (
                        <button key={f} onClick={() => setFilterIssuer(f)} className={`text-xs font-semibold px-3 py-1 rounded-full border transition-all ${filterIssuer === f ? 'bg-[#002776] text-white border-[#002776]' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}>{f}</button>
                    ))}
                </div>
                <div className="flex gap-1 ml-4">
                    {['All', 'High', 'Medium', 'Low'].map(f => (
                        <button key={f} onClick={() => setFilterImpact(f)} className={`text-xs font-semibold px-3 py-1 rounded-full border transition-all ${filterImpact === f ? 'bg-[#002776] text-white border-[#002776]' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}>{f}</button>
                    ))}
                </div>
            </div>

            {/* Update cards */}
            <div className="space-y-3">
                {filtered.map(doc => (
                    <div key={doc.id} className={`bg-white rounded-xl border shadow-sm overflow-hidden transition-all ${!doc.is_promoted ? 'border-orange-200 border-l-4 border-l-orange-400' : 'border-gray-100'}`}>
                        <div className="p-5 cursor-pointer hover:bg-gray-50" onClick={() => setExpanded(expanded === doc.id ? null : doc.id)}>
                            <div className="flex items-start justify-between gap-4">
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${issuerColor[doc.issuer] ?? 'bg-gray-100 text-gray-700'}`}>{doc.issuer}</span>
                                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${impactColor[doc.impact] ?? impactColor.Low}`}>{doc.impact} Impact</span>
                                        {!doc.is_promoted && <span className="text-xs font-semibold text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full flex items-center gap-1"><Clock className="w-3 h-3" />Unreviewed</span>}
                                        {doc.is_promoted && <span className="text-xs font-semibold text-green-600 bg-green-50 px-2 py-0.5 rounded-full flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Acknowledged</span>}
                                    </div>
                                    <h3 className="font-semibold text-gray-900">{doc.title}</h3>
                                    {(doc.effectiveDate || doc.postedDate) && (
                                        <div className="text-xs text-gray-400 mt-1">{doc.effectiveDate ? `Effective ${doc.effectiveDate}` : ''}{doc.postedDate ? ` · Posted ${doc.postedDate}` : ''}</div>
                                    )}
                                </div>
                            </div>
                        </div>
                        {expanded === doc.id && (
                            <div className="border-t border-gray-50 px-5 py-4">
                                <p className="text-sm text-gray-700 leading-relaxed mb-4">{doc.summary}</p>
                                <div className="flex items-center gap-3">
                                    {doc.source_url && (
                                        <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-xs font-semibold text-[#002776] hover:underline">
                                            <ExternalLink className="w-3.5 h-3.5" />View on official source
                                        </a>
                                    )}
                                    {!doc.is_promoted && (
                                        <button
                                            onClick={() => acknowledge(doc)}
                                            disabled={promoting === doc.id}
                                            className="ml-auto flex items-center gap-1.5 text-xs font-semibold bg-[#002776] text-white px-4 py-1.5 rounded-lg hover:bg-[#001a54] disabled:opacity-50"
                                        >
                                            {promoting === doc.id ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                            Acknowledge & Log
                                        </button>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </AuditShell>
    )
}
