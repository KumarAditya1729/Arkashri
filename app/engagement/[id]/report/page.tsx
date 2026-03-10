'use client'

import { useState, use, useEffect } from 'react'
import { FileText, Download, CheckCircle2, AlertTriangle, Eye, Printer, ShieldCheck, PenTool, Loader2 } from 'lucide-react'
import { getEngagement, EngagementResponse, getSealSession, createSealSession, signSealSession, SealSessionOut, PartnerRole } from '@/lib/api'
import { Badge } from '@/components/ui/badge'

const execContent = `The audit of the entity for the specified period was conducted in accordance with Standards on Auditing (SAs) issued by the ICAI. Based on our procedures, we have identified relevant risks and key findings requiring management attention.

The entity's internal control framework is substantially effective, with one deficiency noted in payroll pre-posting variance analysis. We recommend immediate remediation.`

const findingsContent = `1. Revenue Recognition (RSK-001) — CRITICAL: Timing differences of Rs.18L identified across 3 invoices crossing period end. Management explanation received; adjustment booked.

2. Payroll Cut-Off (RSK-002) — HIGH: 3 out of 20 sampled payroll records showed variances exceeding 5% tolerance. Management to strengthen pre-posting review.

3. Related Party Transactions (RSK-004) — CRITICAL: Disclosure in financial statements is incomplete. 2 subsidiary balances excluded from notes. Immediate rectification required before sign-off.`

const controlsContent = `Internal controls over financial reporting are assessed as substantially effective. One material weakness has been identified in the payroll area (CTL-034). All other tested controls (5 of 6) are operating effectively.

We recommend the company strengthen its payroll pre-posting review procedure and implement mandatory dual approval above Rs.5L payroll adjustments.`

interface Section {
    id: string
    title: string
    content: string
    status: 'complete' | 'in-progress' | 'pending'
    wordCount: number
}

const SECTIONS: Section[] = []

const statusConfig = {
    complete: { color: 'text-green-600 bg-green-100', label: 'Complete', icon: CheckCircle2 },
    'in-progress': { color: 'text-blue-600 bg-blue-100', label: 'In Progress', icon: Eye },
    pending: { color: 'text-gray-500 bg-gray-100', label: 'Pending', icon: AlertTriangle },
}

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params)
    const [active, setActive] = useState('exec')
    const [engagement, setEngagement] = useState<EngagementResponse | null>(null)
    const [sealSession, setSealSession] = useState<SealSessionOut | null>(null)
    const [isSigning, setIsSigning] = useState(false)
    const [content, setContent] = useState<Record<string, string>>(
        Object.fromEntries(SECTIONS.map(s => [s.id, s.content]))
    )

    useEffect(() => {
        getEngagement(id).then(setEngagement).catch(console.error)
        getSealSession(id).then(setSealSession).catch(console.error)
    }, [id])

    const handleCreateSealSession = async () => {
        try {
            const sess = await createSealSession(id, 2)
            setSealSession(sess)
        } catch (err) {
            console.error('Failed to create seal session', err)
        }
    }

    const handleSign = async () => {
        if (!sealSession) return
        setIsSigning(true)
        try {
            const updated = await signSealSession(
                sealSession.id,
                'joint_auditor_001',
                '',
                PartnerRole.JOINT_AUDITOR,
                true // override_ack_confirmed
            )
            setSealSession(updated)
        } catch (err) {
            console.error('Signing failed', err)
        } finally {
            setIsSigning(false)
        }
    }

    const activeSection = SECTIONS.find(s => s.id === active)!
    const totalWords = Object.values(content).reduce((sum, c) => sum + (c.trim() ? c.trim().split(/\s+/).length : 0), 0)
    const complete = SECTIONS.filter(s => s.status === 'complete').length

    const isJointSignatureRequired = engagement?.engagement_type === 'statutory_audit' || engagement?.engagement_type === 'external_audit'

    return (
        <>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#002776] tracking-tight">Phase 7: Audit Report</h1>
                    <p className="text-gray-500 mt-1 text-xs text-balance">Draft, review and finalise the audit opinion and report for ENG-{id}.</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => console.log('Preview clicked')} className="flex items-center gap-2 border border-gray-100 text-gray-700 text-[10px] font-bold px-4 py-1.5 rounded-lg hover:bg-gray-50 transition-colors uppercase tracking-widest">
                        <Printer className="w-3.5 h-3.5" /> Preview
                    </button>
                    <button onClick={() => console.log('Export PDF clicked')} className="flex items-center gap-2 bg-[#002776] text-white text-[10px] font-bold px-4 py-1.5 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm uppercase tracking-widest">
                        <Download className="w-3.5 h-3.5" /> Export PDF
                    </button>
                </div>
            </div>

            {/* Progress summary */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {[
                    { label: 'Sections Complete', value: `${complete} / ${SECTIONS.length}` },
                    { label: 'Total Word Count', value: totalWords.toLocaleString() },
                    { label: 'Findings Documented', value: '3' },
                ].map(s => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
                        <div className="text-2xl font-black text-gray-900">{s.value}</div>
                        <div className="text-[10px] text-gray-500 mt-1 font-bold uppercase tracking-wider">{s.label}</div>
                    </div>
                ))}
            </div>

            <div className="flex gap-5">
                {/* Section nav */}
                <div className="w-56 flex-shrink-0 space-y-2">
                    {SECTIONS.map(s => {
                        const cfg = statusConfig[s.status as keyof typeof statusConfig]
                        const Icon = cfg.icon
                        return (
                            <button
                                key={s.id}
                                onClick={() => setActive(s.id)}
                                className={`w-full text-left px-4 py-3 rounded-xl border transition-all ${active === s.id ? 'bg-[#002776] text-white border-[#002776] shadow-md' : 'bg-white border-gray-100 text-gray-700 hover:border-gray-200 hover:shadow-sm'}`}
                            >
                                <div className="font-bold text-xs uppercase tracking-tight leading-tight">{s.title}</div>
                                <div className={`text-[10px] mt-1.5 flex items-center gap-1 font-bold uppercase tracking-tighter ${active === s.id ? 'text-blue-200' : cfg.color.replace('bg-', 'text-')}`}>
                                    <Icon className="w-3 h-3" />{cfg.label}
                                    {s.wordCount > 0 && <span className="ml-auto opacity-70">{s.wordCount}W</span>}
                                </div>
                            </button>
                        )
                    })}
                </div>

                {/* Editor */}
                <div className="flex-1 bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden flex flex-col min-h-[500px]">
                    <div className="px-6 py-4 border-b border-gray-50 flex items-center justify-between bg-gray-50/50">
                        <div>
                            <h2 className="font-black text-gray-900 text-xs uppercase tracking-widest">{activeSection.title}</h2>
                            <div className="text-[10px] text-gray-400 mt-0.5 font-bold">
                                {content[active]?.trim().split(/\s+/).filter(Boolean).length || 0} WORDS WRITTEN
                            </div>
                        </div>
                        {activeSection.status === 'complete' && (
                            <span className="flex items-center gap-1 text-[10px] font-bold text-green-600 bg-green-50 px-3 py-1 rounded-full border border-green-200 uppercase tracking-tighter">
                                <CheckCircle2 className="w-3 h-3" /> Signed off by Partner
                            </span>
                        )}
                    </div>

                    {activeSection.status === 'pending' ? (
                        <div className="flex-1 flex items-center justify-center text-center p-12">
                            <div>
                                <FileText className="w-10 h-10 text-gray-100 mx-auto mb-3" />
                                <p className="text-gray-400 text-xs font-bold uppercase tracking-widest">Section Locked</p>
                                <p className="text-gray-300 text-[10px] mt-1 uppercase font-medium">Complete prior sections before drafting this one.</p>
                            </div>
                        </div>
                    ) : (
                        <textarea
                            value={content[active]}
                            onChange={e => setContent(c => ({ ...c, [active]: e.target.value }))}
                            placeholder="Start drafting this section..."
                            className="flex-1 p-8 text-sm text-gray-700 leading-loose resize-none focus:outline-none font-serif bg-white"
                        />
                    )}

                    <div className="px-6 py-4 border-t border-gray-50 flex justify-end gap-2 bg-gray-50/30">
                        <button onClick={() => console.log('Save Local Draft clicked')} className="text-[10px] font-bold border border-gray-200 text-gray-500 px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors uppercase tracking-widest">Save Local Draft</button>
                        <button onClick={() => console.log('Finalize Section clicked')} className="text-[10px] font-bold bg-green-600 text-white px-5 py-2 rounded-lg hover:bg-green-700 transition-all shadow-sm uppercase tracking-widest">Finalize Section</button>
                    </div>
                </div>

                {isJointSignatureRequired && (
                    <div className="w-64 flex-shrink-0 space-y-4">
                        <div className="bg-[#002776] text-white p-4 rounded-xl shadow-lg border border-blue-900">
                            <h3 className="text-[10px] font-black uppercase tracking-widest flex items-center gap-2 mb-3">
                                <ShieldCheck className="w-4 h-4 text-blue-300" />
                                Joint Signature Protocol
                            </h3>
                            <p className="text-[9px] text-blue-100 uppercase font-bold tracking-tighter mb-4">
                                This {engagement?.engagement_type.replace('_', ' ')} requires multi-partner attestation before blockchain sealing.
                            </p>

                            {!sealSession ? (
                                <button
                                    onClick={handleCreateSealSession}
                                    className="w-full flex items-center justify-center gap-2 bg-white/10 hover:bg-white/20 text-white text-[9px] font-black py-2 rounded-lg uppercase tracking-widest border border-white/10 transition-all"
                                >
                                    Initialize Seal Session
                                </button>
                            ) : (
                                <div className="space-y-3">
                                    {sealSession.signatures.map((sig) => (
                                        <div key={sig.id} className="bg-white/10 p-2 rounded-lg border border-white/5">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="text-[8px] font-black uppercase text-blue-200">{sig.role.replace('_', ' ')}</span>
                                                <Badge className="bg-green-500 text-[7px] h-3 px-1">SIGNED</Badge>
                                            </div>
                                            <div className="text-[9px] font-bold">{sig.partner_email.toUpperCase()}</div>
                                        </div>
                                    ))}

                                    {sealSession.status !== 'FULLY_SIGNED' && (
                                        <div className="bg-white/10 p-2 rounded-lg border border-white/5 opacity-60">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="text-[8px] font-black uppercase text-blue-200">Pending Role</span>
                                                <Badge variant="outline" className="text-white border-white/20 text-[7px] h-3 px-1">WAITING</Badge>
                                            </div>
                                            <div className="text-[9px] font-bold italic">AWAITING SIGNATURE...</div>
                                        </div>
                                    )}

                                    {sealSession.status !== 'FULLY_SIGNED' && (
                                        <button
                                            onClick={handleSign}
                                            disabled={isSigning}
                                            className="w-full mt-4 flex items-center justify-center gap-2 bg-blue-500 hover:bg-blue-400 disabled:bg-blue-500/50 text-white text-[9px] font-black py-2 rounded-lg uppercase tracking-widest transition-all shadow-md"
                                        >
                                            {isSigning ? (
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                            ) : (
                                                <PenTool className="w-3 h-3" />
                                            )}
                                            Sign as {sealSession.signatures.length === 0 ? 'Lead Partner' : 'Joint Auditor'}
                                        </button>
                                    )}

                                    {sealSession.status === 'FULLY_SIGNED' && (
                                        <div className="mt-4 bg-green-500/20 border border-green-500/40 p-2 rounded-lg text-center">
                                            <span className="text-[9px] font-black uppercase text-green-300 flex items-center justify-center gap-1">
                                                <ShieldCheck className="w-3 h-3" /> Fully Signed
                                            </span>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl">
                            <h4 className="text-[9px] font-black text-amber-800 uppercase tracking-widest flex items-center gap-2 mb-2">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                Governance Note
                            </h4>
                            <p className="text-[9px] text-amber-900 leading-relaxed font-medium">
                                Cross-jurisdiction co-signing is enabled. Signatures are immutable once applied to the ledger.
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </>
    )
}
