'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { getAdminEvidenceLedger, EvidenceLedgerEntry } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Shield, Database, ExternalLink, Link as LinkIcon, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function AdminLedgerPage() {
    const { user, isAuthenticated } = useAuthStore()
    const [ledger, setLedger] = useState<EvidenceLedgerEntry[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchLedger = async () => {
        setLoading(true)
        try {
            const data = await getAdminEvidenceLedger()
            setLedger(data)
            setError(null)
        } catch (err: any) {
            setError(err.message || 'Failed to fetch evidence ledger')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (isAuthenticated && (user?.role?.toUpperCase() === 'ADMIN')) {
            fetchLedger()
        }
    }, [isAuthenticated, user])

    if (!isAuthenticated || user?.role?.toUpperCase() !== 'ADMIN') {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <CardTitle className="text-red-500">Access Denied</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p>You do not have administrative privileges to view the global evidence ledger.</p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="p-6 space-y-6 max-w-7xl mx-auto">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold flex items-center gap-3">
                        <Shield className="w-8 h-8 text-blue-600" />
                        Universal Evidence Ledger
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Global transparency layer across all tenants and jurisdictions
                    </p>
                </div>
                <Button onClick={fetchLedger} disabled={loading} variant="outline" className="gap-2">
                    <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </Button>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
                    {error}
                </div>
            )}

            {loading && ledger.length === 0 ? (
                <div className="grid gap-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="h-32 bg-gray-100 animate-pulse rounded-xl" />
                    ))}
                </div>
            ) : (
                <div className="grid gap-4">
                    {ledger.length === 0 ? (
                        <Card>
                            <CardContent className="py-10 text-center text-muted-foreground">
                                No anchored evidence found in the global registry.
                            </CardContent>
                        </Card>
                    ) : (
                        ledger.map((entry) => (
                            <Card key={entry.id} className="overflow-hidden border-l-4 border-l-blue-500">
                                <CardContent className="p-0">
                                    <div className="flex flex-col md:flex-row">
                                        <div className="p-4 md:w-1/4 bg-gray-50 border-r border-gray-100 space-y-2">
                                            <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase tracking-wider">
                                                <Database className="w-3 h-3" />
                                                Tenant
                                            </div>
                                            <div className="font-mono text-sm">{entry.tenant_id}</div>
                                            <Badge variant="outline" className="bg-white">
                                                {entry.jurisdiction}
                                            </Badge>
                                        </div>
                                        <div className="p-4 flex-grow space-y-3">
                                            <div className="flex justify-between items-start">
                                                <div>
                                                    <div className="text-xs text-muted-foreground">Merkle Root</div>
                                                    <div className="font-mono text-xs break-all text-blue-700 font-semibold">
                                                        {entry.merkle_root}
                                                    </div>
                                                </div>
                                                <Badge variant="secondary" className="gap-1 capitalize">
                                                    <LinkIcon className="w-3 h-3" />
                                                    {entry.anchor_provider.toLowerCase()}
                                                </Badge>
                                            </div>

                                            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                                                <div>
                                                    <div className="text-xs text-muted-foreground text-xs">Event Range</div>
                                                    <div>{entry.window_start_event_id} → {entry.window_end_event_id}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground text-xs">Anchored At</div>
                                                    <div>{new Date(entry.created_at).toLocaleString()}</div>
                                                </div>
                                                {entry.external_reference && (
                                                    <div className="col-span-2 md:col-span-1">
                                                        <div className="text-xs text-muted-foreground">Ext Ref</div>
                                                        <div className="font-mono text-xs truncate">{entry.external_reference}</div>
                                                    </div>
                                                )}
                                            </div>

                                            {entry.attestations.length > 0 && (
                                                <div className="pt-3 border-t border-dashed border-gray-200">
                                                    <div className="text-xs font-semibold mb-2 text-gray-400 uppercase tracking-widest">Blockchain Attestations</div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {entry.attestations.map((att) => (
                                                            <div key={att.id} className="bg-green-50 text-green-700 px-3 py-1 rounded-full text-xs flex items-center gap-2 border border-green-100">
                                                                <span className="font-bold">{att.network}</span>
                                                                <span className="text-green-300">|</span>
                                                                <span className="font-mono">{att.tx_reference.split('://')[1]?.substring(0, 10)}...</span>
                                                                <a
                                                                    href={att.tx_reference.includes('sim://') ? '#' : `https://polkadot.subscan.io/extrinsic/${att.tx_reference.split('/').pop()}`}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="hover:text-green-900"
                                                                >
                                                                    <ExternalLink className="w-3 h-3" />
                                                                </a>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))
                    )}
                </div>
            )}
        </div>
    )
}
