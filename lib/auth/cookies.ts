import type { NextResponse } from 'next/server'

import {
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_MAX_AGE_SECONDS,
    LEGACY_AUTH_COOKIE_NAMES,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_MAX_AGE_SECONDS,
} from './constants'
import type { BackendAuthResponse } from './types'

type CookieSameSite = 'lax' | 'strict' | 'none'

function getCookieSameSite(): CookieSameSite {
    const configured = process.env.AUTH_COOKIE_SAME_SITE?.trim().toLowerCase()

    if (configured === 'strict' || configured === 'none') {
        return configured
    }

    return 'lax'
}

function getCookieSecure(sameSite: CookieSameSite): boolean {
    const configured = process.env.AUTH_COOKIE_SECURE?.trim().toLowerCase()
    if (configured === 'true') {
        return true
    }
    if (configured === 'false') {
        return sameSite === 'none'
    }

    return process.env.NODE_ENV === 'production' || sameSite === 'none'
}

function getCookieBaseOptions() {
    const sameSite = getCookieSameSite()
    const domain = process.env.AUTH_COOKIE_DOMAIN?.trim() || undefined

    return {
        httpOnly: true,
        secure: getCookieSecure(sameSite),
        sameSite,
        path: '/',
        priority: 'high' as const,
        ...(domain ? { domain } : {}),
    }
}

export function applyAuthCookies(
    response: NextResponse,
    tokens: Pick<BackendAuthResponse, 'access_token' | 'refresh_token'> & Partial<Pick<BackendAuthResponse, 'expires_in'>>,
): void {
    const baseOptions = getCookieBaseOptions()
    const accessTokenMaxAge = typeof tokens.expires_in === 'number' && tokens.expires_in > 0
        ? Math.floor(tokens.expires_in)
        : ACCESS_TOKEN_MAX_AGE_SECONDS

    response.cookies.set(ACCESS_COOKIE_NAME, tokens.access_token, {
        ...baseOptions,
        maxAge: accessTokenMaxAge,
    })
    response.cookies.set(REFRESH_COOKIE_NAME, tokens.refresh_token, {
        ...baseOptions,
        maxAge: REFRESH_TOKEN_MAX_AGE_SECONDS,
    })

    for (const cookieName of LEGACY_AUTH_COOKIE_NAMES) {
        response.cookies.delete(cookieName)
    }
}

export function clearAuthCookies(response: NextResponse): void {
    for (const cookieName of [ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, ...LEGACY_AUTH_COOKIE_NAMES]) {
        response.cookies.set(cookieName, '', {
            ...getCookieBaseOptions(),
            maxAge: 0,
            expires: new Date(0),
        })
    }
}
