'use client'

import { useAuditStore } from '@/store/auditStore'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ShieldAlert, ArrowRight } from 'lucide-react'

interface PhaseApprovalGatewayProps {
    currentPhase: string
    onApprove: () => void
}

export function PhaseApprovalGateway({ currentPhase, onApprove }: PhaseApprovalGatewayProps) {
    const notes = useAuditStore((state) => state.notes)

    // Check if there are any unresolved critical notes blocking the phase
    const unresolvedCritical = notes.filter(n => n.isCritical && !n.resolved)
    const isBlocked = unresolvedCritical.length > 0

    return (
        <Card className={`mt-8 border-2 ${isBlocked ? 'border-red-400 bg-red-50' : 'border-green-400 bg-green-50'}`}>
            <CardContent className="pt-6 pb-6 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    {isBlocked ? (
                        <>
                            <div className="p-3 bg-red-100 rounded-full text-red-600">
                                <ShieldAlert className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-bold text-red-800">Phase Advance Blocked (Maker/Checker)</h3>
                                <p className="text-sm text-red-600">
                                    You cannot proceed past the <strong>{currentPhase}</strong> phase. There are {unresolvedCritical.length} unresolved critical review notes.
                                </p>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="p-3 bg-green-100 rounded-full text-green-600">
                                <ArrowRight className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-bold text-green-800">Ready for Next Phase</h3>
                                <p className="text-sm text-green-600">
                                    All maker/checker validations passed. You may advance the workflow.
                                </p>
                            </div>
                        </>
                    )}
                </div>
                <div>
                    <Button
                        size="lg"
                        variant={isBlocked ? "secondary" : "default"}
                        disabled={isBlocked}
                        onClick={onApprove}
                        className={isBlocked ? "opacity-50 cursor-not-allowed" : "bg-green-600 hover:bg-green-700"}
                    >
                        Approve & Advance
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}
