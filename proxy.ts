import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { applyAuthCookies, clearAuthCookies } from '@/lib/auth/cookies'
import { ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME } from '@/lib/auth/constants'
import { buildRouteTarget, isPublicRoute, sanitizeRedirectTarget } from '@/lib/auth/redirects'
import { AuthApiError, refreshTokenPair, verifyAccessToken } from '@/lib/auth/shared'

async function authenticateRequest(accessToken?: string, refreshToken?: string) {
    if (accessToken) {
        try {
            await verifyAccessToken(accessToken)
            return { authenticated: true as const }
        } catch (error) {
            if (!(error instanceof AuthApiError) || error.status !== 401) {
                return {
                    authenticated: true as const,
                }
            }

            // Fall through to refresh flow.
        }
    }

    if (refreshToken) {
        try {
            const refreshedTokens = await refreshTokenPair(refreshToken)
            return {
                authenticated: true as const,
                refreshedTokens,
            }
        } catch (error) {
            return {
                authenticated: false as const,
                clearCookies: error instanceof AuthApiError && error.status === 401,
            }
        }
    }

    return {
        authenticated: false as const,
        clearCookies: false,
    }
}

export async function proxy(request: NextRequest) {
    const publicRoute = isPublicRoute(request.nextUrl.pathname)
    const accessToken = request.cookies.get(ACCESS_COOKIE_NAME)?.value
    const refreshToken = request.cookies.get(REFRESH_COOKIE_NAME)?.value

    if (!accessToken && !refreshToken) {
        if (publicRoute) {
            return NextResponse.next()
        }

        const redirectUrl = new URL('/sign-in', request.url)
        redirectUrl.searchParams.set(
            'from',
            buildRouteTarget(request.nextUrl.pathname, request.nextUrl.searchParams.toString()),
        )
        return NextResponse.redirect(redirectUrl)
    }

    const auth = await authenticateRequest(accessToken, refreshToken)

    if (!auth.authenticated) {
        if (publicRoute) {
            const response = NextResponse.next()
            if (auth.clearCookies) {
                clearAuthCookies(response)
            }
            return response
        }

        const redirectUrl = new URL('/sign-in', request.url)
        redirectUrl.searchParams.set(
            'from',
            buildRouteTarget(request.nextUrl.pathname, request.nextUrl.searchParams.toString()),
        )

        const response = NextResponse.redirect(redirectUrl)
        if (auth.clearCookies) {
            clearAuthCookies(response)
        }
        return response
    }

    if (publicRoute) {
        const response = NextResponse.redirect(
            new URL(sanitizeRedirectTarget(request.nextUrl.searchParams.get('from')), request.url),
        )
        if (auth.refreshedTokens) {
            applyAuthCookies(response, auth.refreshedTokens)
        }
        return response
    }

    const response = NextResponse.next()
    if (auth.refreshedTokens) {
        applyAuthCookies(response, auth.refreshedTokens)
    }
    return response
}

export const config = {
    matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
