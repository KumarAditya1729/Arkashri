'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { useState, useEffect } from 'react'
import { Eye, CheckCircle2, XCircle, MessageSquare, Clock, ChevronDown, ChevronUp, Send, Loader2 } from 'lucide-react'
import { getApprovals, actionApproval, ApprovalResponse } from '@/lib/api'

type ReviewStatus = 'Approved' | 'Changes Required' | 'Pending' | 'In Review'

// ─── Local seed (used when no approvals in DB yet) ────────────────────────────

interface LocalReview {
    id: string
    section: string
    description: string
    preparedBy: string
    reviewedBy: string
    status: ReviewStatus
    comments: { author: string; text: string; time: string }[]
    backendId?: string    // set when linked to real approval request
}

const SEED_ITEMS: LocalReview[] = []

const statusConfig: Record<ReviewStatus, { icon: any; color: string; bg: string }> = {
    Approved: { icon: CheckCircle2, color: 'text-green-700', bg: 'bg-green-100' },
    'Changes Required': { icon: XCircle, color: 'text-red-700', bg: 'bg-red-100' },
    'In Review': { icon: Eye, color: 'text-blue-700', bg: 'bg-blue-100' },
    Pending: { icon: Clock, color: 'text-gray-600', bg: 'bg-gray-100' },
}

function approvalStatusToReview(s: string): ReviewStatus {
    if (s === 'APPROVED') return 'Approved'
    if (s === 'REJECTED') return 'Changes Required'
    if (s === 'PENDING') return 'Pending'
    return 'In Review'
}

export default function ReviewPage() {
    const [items, setItems] = useState<LocalReview[]>(SEED_ITEMS)
    const [isLive, setIsLive] = useState(false)
    const [loading, setLoading] = useState(false)
    const [expanded, setExpanded] = useState<string | null>('REV-003')
    const [newComment, setNewComment] = useState<Record<string, string>>({})
    const [actioning, setActioning] = useState<string | null>(null)

    useEffect(() => {
        setLoading(true)
        getApprovals().then(data => {
            if (data.length > 0) {
                const mapped: LocalReview[] = data.map((a, i) => ({
                    id: a.id.slice(0, 8).toUpperCase(),
                    section: a.reference_type || `Workpaper ${i + 1}`,
                    description: a.reason || 'Approval request',
                    preparedBy: a.requested_by,
                    reviewedBy: 'Senior Auditor',
                    status: approvalStatusToReview(a.status),
                    backendId: a.id,
                    comments: (a.actions || []).filter(ac => ac.action_type === 'COMMENTED').map(ac => ({
                        author: ac.actor_id,
                        text: ac.notes ?? '',
                        time: new Date(ac.created_at).toLocaleString(),
                    })),
                }))
                setItems(mapped)
                setIsLive(true)
            }
        }).finally(() => setLoading(false))
    }, [])

    const addComment = (id: string) => {
        const text = newComment[id]?.trim()
        if (!text) return
        setItems(its => its.map(it => it.id === id ? {
            ...it,
            comments: [...it.comments, { author: 'Current User', text, time: new Date().toLocaleString() }]
        } : it))
        setNewComment(n => ({ ...n, [id]: '' }))
    }

    const approve = async (id: string) => {
        const item = items.find(it => it.id === id)
        setActioning(id)
        if (item?.backendId) {
            try { await actionApproval(item.backendId, 'APPROVED', 'Approved via UI') } catch { /* fallback */ }
        }
        setItems(its => its.map(it => it.id === id ? { ...it, status: 'Approved' } : it))
        setActioning(null)
    }

    const requestChanges = async (id: string) => {
        const item = items.find(it => it.id === id)
        setActioning(id)
        if (item?.backendId) {
            try { await actionApproval(item.backendId, 'REJECTED', 'Changes requested via UI') } catch { /* fallback */ }
        }
        setItems(its => its.map(it => it.id === id ? { ...it, status: 'Changes Required' } : it))
        setActioning(null)
    }

    return (
        <AuditShell>
            <div className="mb-8">
                <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Audit Workflow</div>
                <div className="flex items-center gap-2 mb-1">
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">Quality Review</h1>
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
                <p className="text-gray-500 mt-1 text-sm">Maker-checker review of all workpapers before final sign-off.</p>
            </div>

            {/* Summary */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {[
                    { label: 'Total Items', value: items.length },
                    { label: 'Approved', value: items.filter(i => i.status === 'Approved').length },
                    { label: 'Changes Required', value: items.filter(i => i.status === 'Changes Required').length },
                    { label: 'Pending', value: items.filter(i => i.status === 'Pending' || i.status === 'In Review').length },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
                        <div className="text-3xl font-black text-gray-900">{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                    </div>
                ))}
            </div>

            <div className="space-y-3">
                {items.map(item => {
                    const cfg = statusConfig[item.status]
                    const Icon = cfg.icon
                    const isOpen = expanded === item.id
                    return (
                        <div key={item.id} className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                            <div className="flex items-start justify-between p-5 cursor-pointer hover:bg-gray-50" onClick={() => setExpanded(isOpen ? null : item.id)}>
                                <div className="flex items-start gap-3">
                                    <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${cfg.color}`} />
                                    <div>
                                        <div className="font-semibold text-gray-900">{item.section}</div>
                                        <div className="text-xs text-gray-400 mt-0.5">{item.id} · Prepared by {item.preparedBy} · Reviewer: {item.reviewedBy}</div>
                                        <div className="text-xs text-gray-500 mt-1">{item.description}</div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 flex-shrink-0 ml-4">
                                    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.bg} ${cfg.color}`}>
                                        <Icon className="w-3 h-3" />{item.status}
                                    </span>
                                    {item.comments.length > 0 && (
                                        <span className="flex items-center gap-1 text-xs text-gray-400"><MessageSquare className="w-3.5 h-3.5" />{item.comments.length}</span>
                                    )}
                                    {isOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                                </div>
                            </div>

                            {isOpen && (
                                <div className="border-t border-gray-50 px-5 pb-5">
                                    {item.comments.length > 0 && (
                                        <div className="mt-4 space-y-3">
                                            {item.comments.map((c, i) => (
                                                <div key={i} className="flex gap-3">
                                                    <div className="w-7 h-7 bg-[#002776] rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                                                        {c.author.split(' ').map(n => n[0]).join('').slice(0, 2)}
                                                    </div>
                                                    <div className="bg-gray-50 rounded-lg px-3 py-2 flex-1">
                                                        <div className="text-xs font-semibold text-gray-700">{c.author} <span className="font-normal text-gray-400">· {c.time}</span></div>
                                                        <div className="text-sm text-gray-800 mt-0.5">{c.text}</div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    <div className="mt-4 flex gap-2">
                                        <input
                                            value={newComment[item.id] || ''}
                                            onChange={e => setNewComment(n => ({ ...n, [item.id]: e.target.value }))}
                                            onKeyDown={e => e.key === 'Enter' && addComment(item.id)}
                                            placeholder="Add a review comment…"
                                            className="flex-1 h-9 px-3 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002776]/30"
                                        />
                                        <button onClick={() => addComment(item.id)} className="px-3 h-9 bg-[#002776] text-white rounded-lg hover:bg-[#001a54] flex items-center gap-1 text-sm">
                                            <Send className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                    {item.status !== 'Approved' && (
                                        <div className="mt-4 flex gap-2">
                                            <button onClick={() => approve(item.id)} disabled={actioning === item.id} className="flex items-center gap-1.5 text-xs font-semibold bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50">
                                                {actioning === item.id ? <Loader2 className="w-3 h-3 animate-spin" /> : null}✓ Approve
                                            </button>
                                            <button onClick={() => requestChanges(item.id)} disabled={actioning === item.id} className="text-xs font-semibold border border-red-200 text-red-600 px-4 py-2 rounded-lg hover:bg-red-50 disabled:opacity-50">
                                                Request Changes
                                            </button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </AuditShell>
    )
}
