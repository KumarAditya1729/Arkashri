'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Activity, Search } from 'lucide-react'

export function ForensicModule() {
    return (
        <Card className="border-l-4 border-l-red-600">
            <CardHeader className="border-b pb-3">
                <CardTitle className="text-lg font-bold text-[#002776] flex items-center">
                    <Search className="w-5 h-5 mr-2 text-red-600" />
                    Forensic Deep Dive Module
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
                <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="bg-slate-50 p-4 rounded-md border flex flex-col items-center justify-center">
                        <span className="text-4xl font-black text-red-600">14</span>
                        <span className="text-sm font-semibold text-gray-600 mt-1 uppercase">Control Deviations</span>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-md border flex flex-col items-center justify-center">
                        <span className="text-4xl font-black text-amber-500">2.4M</span>
                        <span className="text-sm font-semibold text-gray-600 mt-1 uppercase">Identified Exposure ($)</span>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-md border flex flex-col items-center justify-center">
                        <span className="text-4xl font-black text-[#002776]">48</span>
                        <span className="text-sm font-semibold text-gray-600 mt-1 uppercase">Parties Mapped</span>
                    </div>
                </div>

                <div className="border rounded-md p-4 bg-gray-50 flex items-center justify-center h-48">
                    <div className="flex flex-col items-center text-gray-400">
                        <Activity className="w-8 h-8 mb-2" />
                        <p>Pattern Verification Engine Visualization (Placeholder)</p>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
