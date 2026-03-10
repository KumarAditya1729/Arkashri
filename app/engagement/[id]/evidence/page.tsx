'use client'

import { useState, useEffect, useRef, use } from 'react'
import { Upload, Link as LinkIcon, FileText, Image, Eye, Trash2, Plus, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { listEvidence, uploadEvidence, deleteEvidence, EvidenceResponse } from '@/lib/api'
import { getUuid } from '@/lib/engagementRegistry'

type EvidenceType = 'Document' | 'Screenshot' | 'Workpaper' | 'Confirmation' | 'External Link'
type EvidenceStatus = 'Reviewed' | 'Pending Review' | 'Rejected'

const typeIcon: Record<string, any> = { Document: FileText, Screenshot: Image, Confirmation: CheckCircle2, Workpaper: FileText, 'External Link': LinkIcon }
const typeColor: Record<string, string> = { Document: 'text-blue-600 bg-blue-50', Screenshot: 'text-purple-600 bg-purple-50', Confirmation: 'text-green-600 bg-green-50', Workpaper: 'text-orange-600 bg-orange-50', 'External Link': 'text-gray-600 bg-gray-50' }
const statusConfig: Record<string, { color: string; icon: any }> = {
    Reviewed: { color: 'text-green-700 bg-green-100', icon: CheckCircle2 },
    'Pending Review': { color: 'text-orange-700 bg-orange-100', icon: Clock },
    Rejected: { color: 'text-red-700 bg-red-100', icon: Trash2 },
}

const SEED_EVIDENCE: EvidenceResponse[] = []

function toEvType(filename: string): string {
    if (/\.(png|jpg|jpeg|gif)$/i.test(filename)) return 'Screenshot'
    if (/\.(xlsx|xls|csv)$/i.test(filename)) return 'Workpaper'
    return 'Document'
}

export default function EvidencePage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params)
    const uuid = getUuid(id)
    const [evidence, setEvidence] = useState<EvidenceResponse[]>(SEED_EVIDENCE)
    const [isLive, setIsLive] = useState(false)
    const [loading, setLoading] = useState(false)
    const [uploading, setUploading] = useState(false)
    const [dragOver, setDragOver] = useState(false)
    const [filter, setFilter] = useState<string>('All')
    const fileInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (!uuid) return
        setLoading(true)
        listEvidence(uuid).then(data => {
            if (data.length > 0) { setEvidence(data); setIsLive(true) }
        }).finally(() => setLoading(false))
    }, [uuid])

    const handleFiles = async (files: FileList | File[]) => {
        const arr = Array.from(files)
        setUploading(true)
        for (const file of arr) {
            if (uuid) {
                try {
                    const created = await uploadEvidence(uuid, file)
                    setEvidence(ev => [created, ...ev])
                    setIsLive(true)
                } catch {
                    // Local fallback
                    const local: EvidenceResponse = {
                        id: crypto.randomUUID(), engagement_id: '', evd_ref: `EVD-${evidence.length + 1}`.padStart(7, '0'),
                        file_name: file.name, file_path: '', file_size_kb: `${(file.size / 1024).toFixed(0)} KB`,
                        evidence_type: toEvType(file.name), test_ref: null, uploaded_by: 'Current User',
                        ev_status: 'Pending Review', uploaded_at: new Date().toISOString(),
                    }
                    setEvidence(ev => [local, ...ev])
                }
            } else {
                const local: EvidenceResponse = {
                    id: crypto.randomUUID(), engagement_id: '', evd_ref: `EVD-${evidence.length + 1}`.padStart(7, '0'),
                    file_name: file.name, file_path: '', file_size_kb: `${(file.size / 1024).toFixed(0)} KB`,
                    evidence_type: toEvType(file.name), test_ref: null, uploaded_by: 'Current User',
                    ev_status: 'Pending Review', uploaded_at: new Date().toISOString(),
                }
                setEvidence(ev => [local, ...ev])
            }
        }
        setUploading(false)
    }

    const handleDelete = async (item: EvidenceResponse) => {
        if (uuid && !item.id.startsWith('local-')) {
            try { await deleteEvidence(uuid, item.id) } catch { /* fallback */ }
        }
        setEvidence(ev => ev.filter(e => e.id !== item.id))
    }

    const filtered = filter === 'All' ? evidence : evidence.filter(e => e.evidence_type === filter)

    return (
        <>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <h1 className="text-xl font-bold text-[#002776] tracking-tight">Phase 4: Evidence</h1>
                        {isLive ? (
                            <span className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />LIVE
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />LOCAL
                            </span>
                        )}
                        {(loading || uploading) && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
                    </div>
                    <p className="text-gray-500 text-xs text-balance">Upload, link, and manage all audit evidence for ENG-{id}.</p>
                </div>
                <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 bg-[#002776] text-white text-xs font-semibold px-4 py-1.5 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm">
                    <Plus className="w-3.5 h-3.5" /> Add Evidence
                </button>
                <input ref={fileInputRef} type="file" multiple className="hidden" onChange={e => e.target.files && handleFiles(e.target.files)} />
            </div>

            {/* Summary */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {[
                    { label: 'Total Items', value: evidence.length },
                    { label: 'Reviewed', value: evidence.filter(e => e.ev_status === 'Reviewed').length },
                    { label: 'Pending Review', value: evidence.filter(e => e.ev_status === 'Pending Review').length },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
                        <div className="text-3xl font-black text-gray-900">{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                    </div>
                ))}
            </div>

            {/* Drop zone */}
            <div
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
                onClick={() => fileInputRef.current?.click()}
                className={`mb-6 border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer ${dragOver ? 'border-[#002776] bg-blue-50' : 'border-gray-200 bg-gray-50 hover:border-gray-300'}`}
            >
                {uploading ? (
                    <><Loader2 className="w-8 h-8 text-[#002776] mx-auto mb-2 animate-spin" /><p className="text-sm font-medium text-[#002776]">Uploading…</p></>
                ) : (
                    <><Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" /><p className="text-sm font-medium text-gray-600">Drag & drop files here, or <span className="text-[#002776] hover:underline">browse</span></p><p className="text-xs text-gray-400 mt-1 uppercase font-bold tracking-tight">PDF, XLSX, PNG, JPG · MAX 50MB{uuid ? ' · SYNC ENABLED' : ' · LOCAL ONLY'}</p></>
                )}
            </div>

            {/* Filters */}
            <div className="flex gap-2 mb-4 flex-wrap">
                {['All', 'Document', 'Workpaper', 'Screenshot', 'Confirmation', 'External Link'].map(f => (
                    <button key={f} onClick={() => setFilter(f)} className={`text-[10px] font-bold px-3 py-1 rounded-full border uppercase transition-all ${filter === f ? 'bg-[#002776] text-white border-[#002776]' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}>{f}</button>
                ))}
            </div>

            {/* Evidence list */}
            <div className="grid grid-cols-1 gap-3">
                {filtered.map(item => {
                    const Icon = typeIcon[item.evidence_type] ?? FileText
                    const statusCfg = statusConfig[item.ev_status] ?? statusConfig['Pending Review']
                    const StatusIcon = statusCfg.icon
                    const colorClass = typeColor[item.evidence_type] ?? typeColor.Document
                    return (
                        <div key={item.id} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-4 hover:shadow-md transition-shadow">
                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                                <Icon className="w-5 h-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="font-semibold text-gray-900 text-xs truncate">{item.file_name}</div>
                                <div className="text-[10px] text-gray-400 mt-0.5 font-medium uppercase tracking-tighter">
                                    {item.evd_ref} <span className="mx-1">·</span> {item.test_ref ?? 'NO TEST LINKED'} <span className="mx-1">·</span> {item.uploaded_by} <span className="mx-1">·</span> {item.uploaded_at?.slice(0, 10)}{item.file_size_kb ? ` · ${item.file_size_kb}` : ''}
                                </div>
                            </div>
                            <div className="flex items-center gap-3 flex-shrink-0">
                                <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${statusCfg.color}`}>
                                    <StatusIcon className="w-3 h-3" />{item.ev_status}
                                </span>
                                <button onClick={() => handleDelete(item)} className="text-gray-400 hover:text-red-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                            </div>
                        </div>
                    )
                })}
            </div>
        </>
    )
}
