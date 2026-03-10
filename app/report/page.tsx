'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { useState } from 'react'
import { FileText, Download, CheckCircle2, AlertTriangle, Eye, Printer } from 'lucide-react'

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

const SECTIONS: Section[] = [
    {
        id: 'exec',
        title: 'Executive Summary',
        content: execContent,
        status: 'complete',
        wordCount: execContent.trim().split(/\s+/).filter(Boolean).length
    },
    {
        id: 'findings',
        title: 'Key Findings',
        content: findingsContent,
        status: 'complete',
        wordCount: findingsContent.trim().split(/\s+/).filter(Boolean).length
    },
    {
        id: 'controls',
        title: 'Internal Controls',
        content: controlsContent,
        status: 'in-progress',
        wordCount: controlsContent.trim().split(/\s+/).filter(Boolean).length
    }
]

const statusConfig = {
    complete: { color: 'text-green-600 bg-green-100', label: 'Complete', icon: CheckCircle2 },
    'in-progress': { color: 'text-blue-600 bg-blue-100', label: 'In Progress', icon: Eye },
    pending: { color: 'text-gray-500 bg-gray-100', label: 'Pending', icon: AlertTriangle },
}

export default function ReportPage() {
    const [active, setActive] = useState('exec')
    const [content, setContent] = useState<Record<string, string>>(
        Object.fromEntries(SECTIONS.map(s => [s.id, s.content]))
    )

    const activeSection = SECTIONS.find(s => s.id === active) || {
        id: 'exec',
        title: 'Executive Summary',
        content: execContent,
        status: 'complete' as const,
        wordCount: execContent.trim().split(/\s+/).filter(Boolean).length
    }
    const totalWords = Object.values(content).reduce((sum, c) => sum + (c.trim() ? c.trim().split(/\s+/).length : 0), 0)
    const complete = SECTIONS.filter(s => s.status === 'complete').length

    return (
        <AuditShell>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Audit Workflow</div>
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">Audit Report</h1>
                    <p className="text-gray-500 mt-1 text-sm">Draft, review and finalise the audit opinion and report.</p>
                </div>
                <div className="flex gap-2">
                    <button 
                        onClick={() => {
                            // Generate preview of the report
                            const previewContent = Object.values(content).join('\n\n---\n\n')
                            const blob = new Blob([previewContent], { type: 'text/plain' })
                            const url = URL.createObjectURL(blob)
                            window.open(url, '_blank')
                        }} 
                        className="flex items-center gap-2 border border-gray-200 text-gray-700 text-sm font-semibold px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                        <Printer className="w-4 h-4" /> Preview
                    </button>
                    <button 
                        onClick={() => {
                            // Generate and download PDF
                            const reportContent = Object.values(content).join('\n\n---\n\n')
                            
                            // Create a simple HTML structure for PDF
                            const htmlContent = `
                                <html>
                                    <head>
                                        <title>Audit Report</title>
                                        <style>
                                            body { font-family: Arial, sans-serif; margin: 40px; }
                                            h1 { color: #002776; border-bottom: 2px solid #002776; padding-bottom: 10px; }
                                            h2 { color: #333; margin-top: 30px; }
                                            .section { margin-bottom: 20px; }
                                            .status { background: #e8f5e8; padding: 10px; border-radius: 5px; margin: 10px 0; }
                                        </style>
                                    </head>
                                    <body>
                                        <h1>Audit Report</h1>
                                        ${Object.entries(content).map(([id, content]) => `
                                            <div class="section">
                                                <h2>${SECTIONS.find(s => s.id === id)?.title || id}</h2>
                                                <div class="status">${SECTIONS.find(s => s.id === id)?.status || 'pending'}</div>
                                                <div>${content}</div>
                                            </div>
                                        `).join('')}
                                    </body>
                                </html>
                            `
                            
                            // Create blob and download
                            const blob = new Blob([htmlContent], { type: 'text/html' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = `audit-report-${new Date().toISOString().split('T')[0]}.html`
                            document.body.appendChild(a)
                            a.click()
                            document.body.removeChild(a)
                            URL.revokeObjectURL(url)
                        }} 
                        className="flex items-center gap-2 bg-[#002776] text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm"
                    >
                        <Download className="w-4 h-4" /> Export Report
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
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
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
                                className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-all ${active === s.id ? 'bg-[#002776] text-white border-[#002776] shadow-md' : 'bg-white border-gray-100 text-gray-700 hover:border-gray-200 hover:shadow-sm'}`}
                            >
                                <div className="font-semibold leading-tight">{s.title}</div>
                                <div className={`text-xs mt-1 flex items-center gap-1 ${active === s.id ? 'text-blue-200' : cfg.color.split(' ')[0]}`}>
                                    <Icon className="w-3 h-3" />{cfg.label}
                                    {s.wordCount > 0 && <span className="ml-auto">{s.wordCount}w</span>}
                                </div>
                            </button>
                        )
                    })}
                </div>

                {/* Editor */}
                <div className="flex-1 bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden flex flex-col">
                    <div className="px-6 py-4 border-b border-gray-50 flex items-center justify-between">
                        <div>
                            <h2 className="font-bold text-gray-900">{activeSection.title}</h2>
                            <div className="text-xs text-gray-400 mt-0.5">
                                {content[active]?.trim().split(/\s+/).filter(Boolean).length || 0} words
                            </div>
                        </div>
                        {activeSection.status === 'complete' && (
                            <span className="flex items-center gap-1 text-xs font-semibold text-green-600 bg-green-50 px-2.5 py-1 rounded-full border border-green-200">
                                <CheckCircle2 className="w-3 h-3" /> Signed off
                            </span>
                        )}
                    </div>

                    {activeSection.status === 'pending' ? (
                        <div className="flex-1 flex items-center justify-center text-center p-12">
                            <div>
                                <FileText className="w-10 h-10 text-gray-200 mx-auto mb-3" />
                                <p className="text-gray-400 text-sm font-medium">This section has not been started yet.</p>
                                <p className="text-gray-300 text-xs mt-1">Complete prior sections before drafting this one.</p>
                            </div>
                        </div>
                    ) : (
                        <textarea
                            value={content[active]}
                            onChange={e => setContent(c => ({ ...c, [active]: e.target.value }))}
                            placeholder="Start drafting this section..."
                            className="flex-1 p-6 text-sm text-gray-800 leading-relaxed resize-none focus:outline-none font-serif min-h-[420px]"
                        />
                    )}

                    <div className="px-6 py-3 border-t border-gray-50 flex justify-end gap-2">
                        <button onClick={() => console.log('Save Draft clicked')} className="text-xs font-semibold border border-gray-200 text-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50">Save Draft</button>
                        <button onClick={() => console.log('Mark Complete clicked')} className="text-xs font-semibold bg-green-600 text-white px-3 py-1.5 rounded-lg hover:bg-green-700">Mark Complete</button>
                    </div>
                </div>
            </div>
        </AuditShell>
    )
}
