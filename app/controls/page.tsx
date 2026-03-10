'use client'

import { AuditShell } from '@/components/layout/AuditShell'
import { useState } from 'react'
import { Plus, CheckCircle2, XCircle, Clock, ChevronRight, Shield, AlertTriangle } from 'lucide-react'

type ControlStatus = 'Effective' | 'Deficient' | 'Not Tested' | 'Compensating'
type ControlType = 'Preventive' | 'Detective' | 'Corrective'

interface Control {
    id: string
    title: string
    area: string
    type: ControlType
    frequency: string
    owner: string
    status: ControlStatus
    riskRef: string
    lastTested: string
}

const CONTROLS: Control[] = []

const statusConfig: Record<ControlStatus, { icon: any, color: string, bg: string }> = {
    Effective: { icon: CheckCircle2, color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
    Deficient: { icon: XCircle, color: 'text-red-700', bg: 'bg-red-50 border-red-200' },
    'Not Tested': { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200' },
    Compensating: { icon: AlertTriangle, color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200' },
}

const typeColor: Record<ControlType, string> = {
    Preventive: 'bg-blue-100 text-blue-700',
    Detective: 'bg-purple-100 text-purple-700',
    Corrective: 'bg-amber-100 text-amber-800',
}

export default function ControlsPage() {
    const [controls] = useState<Control[]>(CONTROLS)
    const [selected, setSelected] = useState<Control | null>(null)

    const effective = controls.filter(c => c.status === 'Effective').length
    const deficient = controls.filter(c => c.status === 'Deficient').length

    return (
        <AuditShell>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <div className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider">Audit Workflow</div>
                    <h1 className="text-3xl font-black text-[#002776] tracking-tight">Controls Matrix</h1>
                    <p className="text-gray-500 mt-1 text-sm">Evaluate the design and operating effectiveness of internal controls.</p>
                </div>
                <button onClick={() => console.log('Add Control clicked')} className="flex items-center gap-2 bg-[#002776] text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm">
                    <Plus className="w-4 h-4" /> Add Control
                </button>
            </div>

            {/* Summary */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {[
                    { label: 'Total Controls', value: controls.length, color: 'text-[#002776]' },
                    { label: 'Effective', value: effective, color: 'text-green-600' },
                    { label: 'Deficient', value: deficient, color: 'text-red-600' },
                    { label: 'Coverage', value: `${Math.round((effective / controls.length) * 100)}%`, color: 'text-blue-600' },
                ].map((s) => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
                        <div className={`text-3xl font-black ${s.color}`}>{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                    </div>
                ))}
            </div>

            <div className={`flex gap-5 ${selected ? '' : ''}`}>
                {/* Control list */}
                <div className="flex-1 bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                            <tr>
                                <th className="text-left px-5 py-3">ID</th>
                                <th className="text-left px-5 py-3">Control</th>
                                <th className="text-left px-5 py-3">Type</th>
                                <th className="text-left px-5 py-3">Frequency</th>
                                <th className="text-left px-5 py-3">Status</th>
                                <th className="text-left px-5 py-3">Last Tested</th>
                                <th className="px-5 py-3" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {controls.map(ctrl => {
                                const cfg = statusConfig[ctrl.status]
                                const Icon = cfg.icon
                                return (
                                    <tr key={ctrl.id} onClick={() => setSelected(ctrl === selected ? null : ctrl)} className={`hover:bg-gray-50 transition-colors cursor-pointer ${selected?.id === ctrl.id ? 'bg-blue-50' : ''}`}>
                                        <td className="px-5 py-3.5 font-mono text-xs text-gray-500">{ctrl.id}</td>
                                        <td className="px-5 py-3.5 font-medium text-gray-900 max-w-xs">
                                            <div>{ctrl.title}</div>
                                            <div className="text-xs text-gray-400">{ctrl.area} · {ctrl.owner}</div>
                                        </td>
                                        <td className="px-5 py-3.5">
                                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${typeColor[ctrl.type]}`}>{ctrl.type}</span>
                                        </td>
                                        <td className="px-5 py-3.5 text-gray-500 text-xs">{ctrl.frequency}</td>
                                        <td className="px-5 py-3.5">
                                            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border ${cfg.bg} ${cfg.color}`}>
                                                <Icon className="w-3 h-3" />{ctrl.status}
                                            </span>
                                        </td>
                                        <td className="px-5 py-3.5 text-xs text-gray-400 font-mono">{ctrl.lastTested}</td>
                                        <td className="px-5 py-3.5"><ChevronRight className="w-4 h-4 text-gray-300" /></td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>

                {/* Detail panel */}
                {selected && (
                    <div className="w-72 flex-shrink-0 bg-white rounded-xl border border-blue-200 shadow-sm p-5">
                        <div className="flex items-center gap-2 mb-4">
                            <Shield className="w-5 h-5 text-[#002776]" />
                            <span className="font-bold text-gray-900">{selected.id}</span>
                        </div>
                        <h3 className="font-semibold text-gray-900 text-sm mb-4 leading-snug">{selected.title}</h3>
                        <div className="space-y-3 text-sm">
                            {[
                                ['Area', selected.area],
                                ['Type', selected.type],
                                ['Frequency', selected.frequency],
                                ['Owner', selected.owner],
                                ['Linked Risk', selected.riskRef],
                                ['Last Tested', selected.lastTested],
                            ].map(([k, v]) => (
                                <div key={k} className="flex justify-between">
                                    <span className="text-gray-400 text-xs">{k}</span>
                                    <span className="font-medium text-gray-800 text-xs">{v}</span>
                                </div>
                            ))}
                        </div>
                        <div className="mt-5 pt-4 border-t border-gray-100 space-y-2">
                            <button onClick={() => console.log('Mark as Tested clicked')} className="w-full text-xs font-semibold bg-[#002776] text-white py-2 rounded-lg hover:bg-[#001a54]">Mark as Tested</button>
                            <button onClick={() => console.log('Flag as Deficient clicked')} className="w-full text-xs font-semibold border border-red-200 text-red-600 py-2 rounded-lg hover:bg-red-50">Flag as Deficient</button>
                        </div>
                    </div>
                )}
            </div>
        </AuditShell>
    )
}
