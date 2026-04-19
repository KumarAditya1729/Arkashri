'use client'

import { useEffect } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import { AUTH_SESSION_INVALID_EVENT } from '@/lib/auth/constants'
import { buildRouteTarget, isPublicRoute, sanitizeRedirectTarget } from '@/lib/auth/redirects'
import { useAuthStore } from '@/store/authStore'

export function AuthGuard({ children }: { children: React.ReactNode }) {
    const status = useAuthStore((s) => s.status)
    const initialized = useAuthStore((s) => s.initialized)
    const initialize = useAuthStore((s) => s.initialize)
    const setUnauthenticated = useAuthStore((s) => s.setUnauthenticated)
    const router = useRouter()
    const pathname = usePathname()
    const searchParams = useSearchParams()
    const search = searchParams.toString()
    const publicRoute = isPublicRoute(pathname)

    useEffect(() => {
        void initialize()
    }, [initialize])

    useEffect(() => {
        const handleSessionInvalid = () => {
            setUnauthenticated()
        }

        window.addEventListener(AUTH_SESSION_INVALID_EVENT, handleSessionInvalid)
        return () => window.removeEventListener(AUTH_SESSION_INVALID_EVENT, handleSessionInvalid)
    }, [setUnauthenticated])

    useEffect(() => {
        if (!initialized) {
            return
        }

        if (status === 'unauthenticated' && !publicRoute) {
            const target = buildRouteTarget(pathname, search)
            router.replace(`/sign-in?from=${encodeURIComponent(target)}`)
            return
        }

        if (status === 'authenticated' && publicRoute) {
            router.replace(sanitizeRedirectTarget(searchParams.get('from')))
        }
    }, [initialized, pathname, publicRoute, router, search, searchParams, status])

    if (!publicRoute && (!initialized || status === 'loading' || status === 'unauthenticated')) {
        return null
    }

    if (publicRoute && initialized && status === 'authenticated') {
        return null
    }

    return <>{children}</>
}
