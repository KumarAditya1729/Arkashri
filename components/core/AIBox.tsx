'use client'

import { useAuditStore } from '../../store/auditStore'
import { Bot, Info, Crosshair, ExternalLink, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

export function AIBox() {
    const currentStage = useAuditStore((state) => state.currentStage)
    const auditType = useAuditStore((state) => state.auditType)

    // Contextual mock data based on stage
    let contextTopic = ''
    let suggestion = ''
    let confidence = 0

    if (currentStage === 'Dashboard') {
        contextTopic = 'Engagement Overview'
        suggestion = `Based on the active ${auditType || 'Audit'} mandate, there are 4 pending reviews and a missing independence declaration.`
        confidence = 94
    } else if (currentStage === 'Risks') {
        contextTopic = 'Risk Assessment'
        suggestion = `I detected a high variance in Q3 OPEX vs industry baseline. Suggesting the addition of a 'Revenue Recognition' Forensic Procedure.`
        confidence = 88
    } else {
        contextTopic = 'Process Execution'
        suggestion = `Cross-referencing PCAOB standard AS-2315. Please ensure adequate sample sizing is documented.`
        confidence = 98
    }

    return (
        <div className="flex flex-col h-full bg-slate-50">
            <div className="p-4 border-b bg-[#002776] text-white flex items-center gap-2">
                <Bot className="w-5 h-5 text-[#92d400]" />
                <h2 className="font-semibold text-sm">Contextual AI Assistant</h2>
            </div>

            <ScrollArea className="flex-1">
                <div className="p-5 flex flex-col gap-6">
                    {/* Active Context */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest flex items-center">
                                <Crosshair className="w-3 h-3 mr-1" /> Contextual Lens
                            </h3>
                        </div>
                        <div className="p-3 bg-white border rounded-md text-sm shadow-sm font-medium">
                            {contextTopic}: {auditType || 'Generic Engagement'}
                        </div>
                    </div>

                    {/* Suggestion Card */}
                    <div className="border border-indigo-100 rounded-lg bg-indigo-50/50 shadow-sm overflow-hidden">
                        <div className="bg-indigo-100/50 px-3 py-2 border-b border-indigo-100 flex justify-between items-center">
                            <span className="text-xs font-bold text-indigo-800 uppercase">Grounded Suggestion</span>
                            <Badge variant="outline" className="text-indigo-700 bg-white border-indigo-200">
                                AI-9173A
                            </Badge>
                        </div>
                        <div className="p-4">
                            <p className="text-sm text-gray-800 mb-4 leading-relaxed">
                                {suggestion}
                            </p>

                            <div className="flex justify-between items-center bg-white p-2 rounded border text-xs">
                                <span className="text-gray-500 flex items-center">
                                    <Activity className="w-3 h-3 mr-1" /> Confidence
                                </span>
                                <span className="font-bold text-indigo-700">{confidence}%</span>
                            </div>
                        </div>
                        <div className="bg-white px-4 py-3 border-t flex justify-end gap-2">
                            <Button variant="ghost" size="sm" className="text-gray-500" onClick={() => console.log('AI suggestion dismissed')}>Dismiss</Button>
                            <Button size="sm" className="bg-[#002776] hover:bg-[#001f5c]" onClick={() => console.log('AI action applied')}>Apply Action</Button>
                        </div>
                    </div>

                    {/* Compliance Source */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-2 flex items-center">
                            <Info className="w-3 h-3 mr-1" /> Regulatory Binding
                        </h3>
                        <ul className="space-y-2">
                            <li className="text-sm p-2 border rounded bg-white flex justify-between items-center cursor-pointer hover:border-gray-400">
                                <span className="truncate mr-2">ISA 315 (Revised 2019)</span>
                                <ExternalLink className="w-3 h-3 text-gray-400 shrink-0" />
                            </li>
                            <li className="text-sm p-2 border rounded bg-white flex justify-between items-center cursor-pointer hover:border-gray-400">
                                <span className="truncate mr-2">PCAOB AS 2110</span>
                                <ExternalLink className="w-3 h-3 text-gray-400 shrink-0" />
                            </li>
                        </ul>
                    </div>

                </div>
            </ScrollArea>
        </div>
    )
}
