import { DEFAULT_AUTH_REDIRECT, PUBLIC_ROUTES } from './constants'

export function isPublicRoute(pathname: string): boolean {
    return PUBLIC_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))
}

export function buildRouteTarget(pathname: string, search: string): string {
    return `${pathname}${search ? `?${search}` : ''}`
}

export function sanitizeRedirectTarget(target: string | null | undefined, fallback = DEFAULT_AUTH_REDIRECT): string {
    if (!target || !target.startsWith('/') || target.startsWith('//')) {
        return fallback
    }

    if (target.startsWith('/api/')) {
        return fallback
    }

    if (PUBLIC_ROUTES.some((route) => target === route || target.startsWith(`${route}/`) || target.startsWith(`${route}?`))) {
        return fallback
    }

    return target
}

