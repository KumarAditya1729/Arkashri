'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { useState } from 'react'
import { Plus, CheckCircle2, XCircle, Clock, FlaskConical, ChevronRight } from 'lucide-react'

type TestStatus = 'Pass' | 'Fail' | 'In Progress' | 'Pending'

interface TestProcedure {
    id: string
    procedure: string
    area: string
    controlRef: string
    assignee: string
    status: TestStatus
    sampleSize: number
    exceptions: number
    dueDate: string
}

const TESTS: TestProcedure[] = []

const statusConfig: Record<TestStatus, { icon: any, color: string, bg: string }> = {
    Pass: { icon: CheckCircle2, color: 'text-green-700', bg: 'bg-green-100' },
    Fail: { icon: XCircle, color: 'text-red-700', bg: 'bg-red-100' },
    'In Progress': { icon: Clock, color: 'text-blue-700', bg: 'bg-blue-100' },
    Pending: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100' },
}

export default function TestingPage() {
    const [tests, setTests] = useState<TestProcedure[]>(TESTS)
    const [selected, setSelected] = useState<TestProcedure | null>(null)
    const [notes, setNotes] = useState<Record<string, string>>({})

    const pass = tests.filter(t => t.status === 'Pass').length
    const fail = tests.filter(t => t.status === 'Fail').length
    const totalExceptions = tests.reduce((sum, t) => sum + t.exceptions, 0)

    const updateStatus = (id: string, status: TestStatus) => {
        setTests(ts => ts.map(t => t.id === id ? { ...t, status } : t))
        setSelected(s => s?.id === id ? { ...s, status } : s)
    }

    return (
        <AuditShell>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Audit Workflow</div>
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">Testing</h1>
                    <p className="text-gray-500 mt-1 text-sm">Execute audit test procedures and record results and exceptions.</p>
                </div>
                <button onClick={() => console.log('Add Test clicked')} className="flex items-center gap-2 bg-[#002776] text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm">
                    <Plus className="w-4 h-4" /> Add Test
                </button>
            </div>

            {/* Summary */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {[
                    { label: 'Total Tests', value: tests.length, color: 'text-[#002776]' },
                    { label: 'Passed', value: pass, color: 'text-green-600' },
                    { label: 'Failed', value: fail, color: 'text-red-600' },
                    { label: 'Exceptions', value: totalExceptions, color: 'text-orange-500' },
                ].map((s) => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
                        <div className={`text-3xl font-black ${s.color}`}>{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                    </div>
                ))}
            </div>

            <div className="flex gap-5">
                <div className="flex-1 space-y-3">
                    {tests.map(test => {
                        const cfg = statusConfig[test.status]
                        const Icon = cfg.icon
                        return (
                            <div
                                key={test.id}
                                onClick={() => setSelected(test === selected ? null : test)}
                                className={`bg-white rounded-xl border p-5 cursor-pointer transition-all hover:shadow-md ${selected?.id === test.id ? 'border-blue-300 shadow-md' : 'border-gray-100'} ${test.exceptions > 0 ? 'border-l-4 border-l-red-400' : ''}`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex items-start gap-3">
                                        <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${cfg.color}`} />
                                        <div>
                                            <div className="font-semibold text-gray-900 text-sm">{test.procedure}</div>
                                            <div className="text-xs text-gray-400 mt-0.5">{test.id} · {test.area} · {test.controlRef} · Due {test.dueDate}</div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3 flex-shrink-0">
                                        {test.sampleSize > 0 && (
                                            <div className="text-right">
                                                <div className="text-xs text-gray-400">Sample / Exceptions</div>
                                                <div className="text-sm font-bold text-gray-700">{test.sampleSize} / <span className={test.exceptions > 0 ? 'text-red-600' : 'text-green-600'}>{test.exceptions}</span></div>
                                            </div>
                                        )}
                                        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1 ${cfg.bg} ${cfg.color}`}>
                                            <Icon className="w-3 h-3" />{test.status}
                                        </span>
                                        <ChevronRight className="w-4 h-4 text-gray-300" />
                                    </div>
                                </div>
                                <div className="mt-2 text-xs text-gray-400">Assigned to <span className="text-gray-600 font-medium">{test.assignee}</span></div>
                            </div>
                        )
                    })}
                </div>

                {/* Detail side panel */}
                {selected && (
                    <div className="w-72 flex-shrink-0 bg-white rounded-xl border border-blue-200 shadow-sm p-5">
                        <div className="flex items-center gap-2 mb-4">
                            <FlaskConical className="w-5 h-5 text-[#002776]" />
                            <span className="font-bold text-gray-900 text-sm">{selected.id}</span>
                        </div>
                        <p className="text-sm text-gray-800 font-medium mb-5 leading-snug">{selected.procedure}</p>

                        <div className="space-y-3 text-xs mb-5">
                            {[
                                ['Area', selected.area],
                                ['Control', selected.controlRef],
                                ['Assignee', selected.assignee],
                                ['Due Date', selected.dueDate],
                                ['Sample Size', selected.sampleSize],
                                ['Exceptions', selected.exceptions],
                            ].map(([k, v]) => (
                                <div key={String(k)} className="flex justify-between">
                                    <span className="text-gray-400">{k}</span>
                                    <span className={`font-semibold ${k === 'Exceptions' && Number(v) > 0 ? 'text-red-600' : 'text-gray-800'}`}>{String(v)}</span>
                                </div>
                            ))}
                        </div>

                        <textarea
                            value={notes[selected.id] || ''}
                            onChange={e => setNotes(n => ({ ...n, [selected.id]: e.target.value }))}
                            placeholder="Add working notes..."
                            className="w-full text-xs border border-gray-200 rounded-lg p-2 min-h-[80px] resize-none focus:outline-none focus:ring-1 focus:ring-[#002776]/30 mb-4"
                        />

                        <div className="space-y-2">
                            <button onClick={() => updateStatus(selected.id, 'Pass')} className="w-full text-xs font-semibold bg-green-600 text-white py-2 rounded-lg hover:bg-green-700">✓ Mark Pass</button>
                            <button onClick={() => updateStatus(selected.id, 'Fail')} className="w-full text-xs font-semibold bg-red-600 text-white py-2 rounded-lg hover:bg-red-700">✗ Mark Fail</button>
                            <button onClick={() => updateStatus(selected.id, 'In Progress')} className="w-full text-xs font-semibold border border-gray-200 text-gray-700 py-2 rounded-lg hover:bg-gray-50">Start Testing</button>
                        </div>
                    </div>
                )}
            </div>
        </AuditShell>
    )
}
