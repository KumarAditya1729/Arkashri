'use client'

import { useAuditStore } from '@/store/auditStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AlertTriangle, Plus } from 'lucide-react'
import { ThreadedCommentary } from '@/components/audit/ThreadedCommentary'

export function RiskModule() {
    const risks = useAuditStore((state) => state.risks)
    const addRisk = useAuditStore((state) => state.addRisk)

    const handleAddSampleRisk = () => {
        addRisk({
            id: `RSK-${Math.floor(Math.random() * 1000)}`,
            title: 'Identified Process Anomaly',
            score: Math.floor(Math.random() * 10) + 1,
            status: 'Open',
        })
    }

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 border-b">
                <CardTitle className="text-lg font-bold text-[#002776] flex items-center">
                    <AlertTriangle className="w-5 h-5 mr-2 text-amber-500" />
                    Risk Assessment Module
                </CardTitle>
                <Button variant="outline" size="sm" onClick={handleAddSampleRisk}>
                    <Plus className="w-4 h-4 mr-1" /> Add Risk
                </Button>
            </CardHeader>
            <CardContent className="pt-4">
                {risks.length === 0 ? (
                    <div className="text-center p-6 text-gray-500 bg-gray-50 rounded-md">
                        No risks identified in this engagement yet.
                    </div>
                ) : (
                    <div className="grid gap-3">
                        {risks.map((risk) => (
                            <div key={risk.id} className="flex flex-col gap-2 p-3 border rounded-md bg-white shadow-sm">
                                <div className="flex justify-between items-center">
                                    <div>
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-semibold text-sm">{risk.id}</span>
                                            <Badge variant={risk.status === 'Open' ? 'destructive' : 'secondary'}>{risk.status}</Badge>
                                        </div>
                                        <p className="text-sm text-gray-700">{risk.title}</p>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-xs text-gray-500 uppercase font-semibold">Assessed Risk Level</div>
                                        <div className={`text-xl font-black ${risk.score >= 8 ? 'text-red-600' : risk.score >= 5 ? 'text-yellow-600' : 'text-green-600'}`}>
                                            {risk.score >= 8 ? 'HIGH' : risk.score >= 5 ? 'MEDIUM' : 'LOW'}
                                        </div>
                                    </div>
                                </div>
                                <ThreadedCommentary targetId={risk.id} targetType="Risk" />
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}
