'use client'

import { useEffect, useRef } from 'react'
import { useAuditStore } from '@/store/auditStore'

interface EngagementStateInitializerProps {
    engagementId: string
    auditType: string
}

export function EngagementStateInitializer({ engagementId, auditType }: EngagementStateInitializerProps) {
    // Prevent double-initialization in React Strict Mode
    const initialized = useRef(false)
    const setEngagement = useAuditStore((state) => state.setEngagement)

    useEffect(() => {
        if (!initialized.current) {
            setEngagement(engagementId, auditType)
            initialized.current = true
        }
    }, [engagementId, auditType, setEngagement])

    return null // Renderless setup component
}
