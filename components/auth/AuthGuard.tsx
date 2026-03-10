'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuthStore } from '../../store/authStore'

const PUBLIC_ROUTES = ['/sign-in', '/register']

export function AuthGuard({ children }: { children: React.ReactNode }) {
    const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
    const router = useRouter()
    const pathname = usePathname()
    const [isMounted, setIsMounted] = useState(false)

    useEffect(() => {
        setIsMounted(true)
    }, [])

    useEffect(() => {
        if (isMounted && !isAuthenticated && !PUBLIC_ROUTES.some((r) => pathname.startsWith(r))) {
            router.replace(`/sign-in?from=${encodeURIComponent(pathname)}`)
        }
    }, [isMounted, isAuthenticated, pathname, router])

    // Prevent hydration mismatch: wait for client mount
    if (!isMounted) {
        // If it's a public route, it's safe to server-render
        if (PUBLIC_ROUTES.some((r) => pathname.startsWith(r))) {
            return <>{children}</>
        }
        // Protected routes return nothing during SSR to avoid flashing unauthorized content
        return null
    }

    if (!isAuthenticated && !PUBLIC_ROUTES.some((r) => pathname.startsWith(r))) {
        return null
    }

    return <>{children}</>
}
