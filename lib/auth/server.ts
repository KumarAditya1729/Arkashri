import 'server-only'

import { ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME } from './constants'
import { AuthApiError, buildAuthSession, refreshTokenPair, verifyAccessToken } from './shared'
import type { AuthSession, BackendAuthResponse } from './types'

export interface AuthCookieSnapshot {
    accessToken?: string
    refreshToken?: string
}

export interface ResolvedServerAuth {
    session: AuthSession
    accessToken: string
    refreshedTokens?: BackendAuthResponse
}

export interface UnresolvedServerAuth {
    session: null
    accessToken: null
    clearCookies: boolean
}

export type ServerAuthResolution = ResolvedServerAuth | UnresolvedServerAuth

export function readAuthCookies(cookieStore: {
    get(name: string): { value: string } | undefined
}): AuthCookieSnapshot {
    return {
        accessToken: cookieStore.get(ACCESS_COOKIE_NAME)?.value,
        refreshToken: cookieStore.get(REFRESH_COOKIE_NAME)?.value,
    }
}

export async function resolveServerAuth(cookies: AuthCookieSnapshot): Promise<ServerAuthResolution> {
    if (cookies.accessToken) {
        try {
            const verified = await verifyAccessToken(cookies.accessToken)
            return {
                session: buildAuthSession(verified.user),
                accessToken: cookies.accessToken,
            }
        } catch (error) {
            if (!(error instanceof AuthApiError) || error.status !== 401) {
                throw error
            }
        }
    }

    if (cookies.refreshToken) {
        try {
            const refreshedTokens = await refreshTokenPair(cookies.refreshToken)
            return {
                session: buildAuthSession(refreshedTokens.user),
                accessToken: refreshedTokens.access_token,
                refreshedTokens,
            }
        } catch (error) {
            if (!(error instanceof AuthApiError) || error.status !== 401) {
                throw error
            }

            return {
                session: null,
                accessToken: null,
                clearCookies: true,
            }
        }
    }

    return {
        session: null,
        accessToken: null,
        clearCookies: false,
    }
}
