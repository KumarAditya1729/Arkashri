'use client'

import { useState, use } from 'react'
import { Calendar, Users, Target, ChevronRight, Plus, CheckCircle2, Clock, AlertCircle, FileText } from 'lucide-react'

interface Phase {
    id: string
    name: string
    status: 'completed' | 'in-progress' | 'upcoming'
    startDate: string
    endDate: string
    owner: string
    progress: number
}

interface TeamMember {
    name: string
    role: string
    initials: string
    color: string
}

interface ScopeItem {
    area: string
    included: boolean
    materialityThreshold: string
}

const PHASES: Phase[] = []
const TEAM: TeamMember[] = []
const SCOPE: ScopeItem[] = []

const statusConfig = {
    completed: { icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50 border-green-200', label: 'Completed' },
    'in-progress': { icon: Clock, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200', label: 'In Progress' },
    upcoming: { icon: AlertCircle, color: 'text-gray-400', bg: 'bg-gray-50 border-gray-200', label: 'Upcoming' },
}

export default function PlanningPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params)
    const [activeTab, setActiveTab] = useState<'timeline' | 'scope' | 'team'>('timeline')
    const [materiality, setMateriality] = useState('2500000')

    return (
        <>
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#002776] tracking-tight">Phase 1: Planning</h1>
                    <p className="text-gray-500 mt-1 text-xs">Define audit strategy, scope, timeline, and team assignments for ENG-{id}.</p>
                </div>
                <button onClick={() => console.log('New Phase clicked')} className="flex items-center gap-2 bg-[#002776] text-white text-xs font-semibold px-4 py-1.5 rounded-lg hover:bg-[#001a54] transition-colors shadow-sm">
                    <Plus className="w-3.5 h-3.5" /> New Phase
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {[
                    { label: 'Total Phases', value: '5', icon: FileText, color: 'text-[#002776]' },
                    { label: 'Days Remaining', value: '38', icon: Calendar, color: 'text-orange-500' },
                    { label: 'Team Members', value: '4', icon: Users, color: 'text-green-600' },
                ].map((s) => (
                    <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-lg bg-gray-50 flex items-center justify-center ${s.color}`}>
                            <s.icon className="w-5 h-5" />
                        </div>
                        <div>
                            <div className="text-2xl font-black text-gray-900">{s.value}</div>
                            <div className="text-xs text-gray-500">{s.label}</div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 mb-5 bg-gray-100 p-1 rounded-lg w-fit">
                {(['timeline', 'scope', 'team'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-4 py-1 rounded-md text-xs font-semibold capitalize transition-all ${activeTab === tab ? 'bg-white shadow-sm text-[#002776]' : 'text-gray-500 hover:text-gray-700'}`}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {/* Timeline tab */}
            {activeTab === 'timeline' && (
                <div className="space-y-3">
                    {PHASES.map((phase) => {
                        const cfg = statusConfig[phase.status as keyof typeof statusConfig]
                        const Icon = cfg.icon
                        return (
                            <div key={phase.id} className={`bg-white rounded-xl border p-5 ${cfg.bg} transition-all hover:shadow-md cursor-pointer`}>
                                <div className="flex items-start justify-between">
                                    <div className="flex items-center gap-3">
                                        <Icon className={`w-5 h-5 ${cfg.color}`} />
                                        <div>
                                            <div className="font-semibold text-gray-900">{phase.name}</div>
                                            <div className="text-xs text-gray-500 mt-0.5">{phase.startDate} → {phase.endDate} · {phase.owner}</div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.color} bg-white/60`}>{cfg.label}</span>
                                        <ChevronRight className="w-4 h-4 text-gray-400" />
                                    </div>
                                </div>
                                {phase.progress > 0 && (
                                    <div className="mt-3">
                                        <div className="flex justify-between text-xs text-gray-500 mb-1">
                                            <span>Progress</span><span>{phase.progress}%</span>
                                        </div>
                                        <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                            <div className="h-full bg-[#002776] rounded-full transition-all" style={{ width: `${phase.progress}%` }} />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Scope tab */}
            {activeTab === 'scope' && (
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                    <div className="p-5 border-b border-gray-50 flex items-center justify-between">
                        <div>
                            <div className="font-semibold text-gray-900">Materiality Threshold</div>
                            <div className="text-xs text-gray-400">Performance materiality applied to all areas below</div>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-gray-500">₹</span>
                            <input
                                type="number"
                                value={materiality}
                                onChange={(e) => setMateriality(e.target.value)}
                                className="w-36 h-9 px-3 border border-gray-200 rounded-lg text-sm font-mono text-right focus:outline-none focus:ring-2 focus:ring-[#002776]/30"
                            />
                        </div>
                    </div>
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                            <tr>
                                <th className="text-left px-5 py-3">Audit Area</th>
                                <th className="text-center px-5 py-3">Included</th>
                                <th className="text-right px-5 py-3">Materiality Floor</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {SCOPE.map((s) => (
                                <tr key={s.area} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-5 py-3.5 font-medium text-gray-900">{s.area}</td>
                                    <td className="px-5 py-3.5 text-center">
                                        {s.included
                                            ? <CheckCircle2 className="w-5 h-5 text-green-500 mx-auto" />
                                            : <span className="text-gray-300">—</span>
                                        }
                                    </td>
                                    <td className="px-5 py-3.5 text-right font-mono text-gray-700">{s.materialityThreshold}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Team tab */}
            {activeTab === 'team' && (
                <div className="grid grid-cols-2 gap-4">
                    {TEAM.map((member) => (
                        <div key={member.name} className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4 hover:shadow-md transition-shadow cursor-pointer">
                            <div className={`w-12 h-12 rounded-full ${member.color} flex items-center justify-center text-white font-bold text-sm flex-shrink-0`}>
                                {member.initials}
                            </div>
                            <div>
                                <div className="font-semibold text-gray-900">{member.name}</div>
                                <div className="text-sm text-gray-500">{member.role}</div>
                            </div>
                        </div>
                    ))}
                    <button onClick={() => console.log('Add Team Member clicked')} className="bg-gray-50 border-2 border-dashed border-gray-200 rounded-xl p-5 flex items-center gap-4 hover:border-[#002776] hover:bg-blue-50 transition-colors text-gray-400 hover:text-[#002776]">
                        <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                            <Plus className="w-5 h-5" />
                        </div>
                        <span className="font-semibold text-sm">Add Team Member</span>
                    </button>
                </div>
            )}
        </>
    )
}
