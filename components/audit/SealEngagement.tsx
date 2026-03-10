'use client'

import { useState } from 'react'
import { sealEngagement, SealResponse, ApiError } from '@/lib/api'
import { Lock, Loader2, CheckCircle2, AlertCircle, ExternalLink } from 'lucide-react'

interface SealEngagementProps {
    engagementUuid: string
    alreadySealed: boolean
    sealHash?: string | null
    sealedAt?: string | null
}

export function SealEngagement({ engagementUuid, alreadySealed, sealHash, sealedAt }: SealEngagementProps) {
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [result, setResult] = useState<SealResponse | null>(null)
    const [sealed, setSealed] = useState(alreadySealed)
    const [existingHash] = useState(sealHash)
    const [existingTs] = useState(sealedAt)

    async function handleSeal() {
        if (!engagementUuid || sealed) return
        setLoading(true)
        setError(null)
        try {
            const res = await sealEngagement(engagementUuid)
            setResult(res)
            setSealed(true)
        } catch (err) {
            if (err instanceof ApiError) {
                setError(`API ${err.status}: ${err.message}`)
            } else {
                setError('Unexpected error. Check backend connection.')
            }
        } finally {
            setLoading(false)
        }
    }

    const displayHash = result?.seal.hash ?? existingHash
    const displayTs = result?.seal.payload.metadata.seal_timestamp_utc
        ?? (existingTs ? new Date(existingTs).toISOString() : null)

    if (sealed && displayHash) {
        return (
            <div className="rounded-xl border border-green-200 bg-green-50 p-4 mt-4">
                <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                    <span className="text-sm font-bold text-green-800">Engagement Sealed 🔒</span>
                    {displayTs && (
                        <span className="text-xs text-green-600 ml-auto font-mono">
                            {new Date(displayTs).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
                        </span>
                    )}
                </div>
                <div className="bg-white rounded-lg border border-green-100 px-3 py-2">
                    <div className="text-xs text-gray-500 mb-0.5">SHA-256 Seal Hash</div>
                    <div className="font-mono text-xs text-gray-800 break-all">{displayHash}</div>
                </div>
                {result && (
                    <div className="mt-2 text-xs text-green-700">
                        Signed by <span className="font-semibold">{result.seal.signer}</span> ·{' '}
                        Merkle root: <span className="font-mono">{result.seal.payload.cryptographic_anchors.audit_event_merkle_root?.slice(0, 16) ?? 'none'}…</span>
                    </div>
                )}
            </div>
        )
    }

    return (
        <div className="mt-4">
            {error && (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg px-3 py-2 mb-3">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    {error}
                </div>
            )}
            <button
                onClick={handleSeal}
                disabled={loading || !engagementUuid}
                className="flex items-center gap-2 px-4 py-2.5 bg-[#002776] hover:bg-[#001a54] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-all shadow-sm hover:shadow-md"
            >
                {loading ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Sealing…</>
                ) : (
                    <><Lock className="w-4 h-4" /> Seal Engagement</>
                )}
            </button>
            <p className="text-xs text-gray-400 mt-1.5">
                Generates a cryptographically signed WORM bundle and writes seal hash to the audit ledger.
            </p>
        </div>
    )
}
