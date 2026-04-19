import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

import { clearAuthCookies, applyAuthCookies } from '@/lib/auth/cookies'
import { DEFAULT_JURISDICTION } from '@/lib/auth/constants'
import { requestWebSocketTicket, AuthApiError } from '@/lib/auth/shared'
import { readAuthCookies, resolveServerAuth } from '@/lib/auth/server'

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' }

export async function GET(request: Request) {
    const cookieStore = await cookies()
    const auth = await resolveServerAuth(readAuthCookies(cookieStore))

    if (!auth.session || !auth.accessToken) {
        const response = NextResponse.json({ error: 'Not authenticated' }, { status: 401, headers: NO_STORE_HEADERS })
        if ('clearCookies' in auth && auth.clearCookies) {
            clearAuthCookies(response)
        }
        return response
    }

    const url = new URL(request.url)
    const jurisdiction = (url.searchParams.get('jurisdiction') || DEFAULT_JURISDICTION).trim().toUpperCase()

    try {
        const ticket = await requestWebSocketTicket(auth.accessToken, jurisdiction)
        const response = NextResponse.json(ticket, {
            headers: NO_STORE_HEADERS,
        })

        if (auth.refreshedTokens) {
            applyAuthCookies(response, auth.refreshedTokens)
        }

        return response
    } catch (error) {
        if (error instanceof AuthApiError) {
            const response = NextResponse.json({ error: error.message }, { status: error.status, headers: NO_STORE_HEADERS })
            if (error.status === 401) {
                clearAuthCookies(response)
            }
            return response
        }

        console.error('WebSocket ticket error:', error)
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500, headers: NO_STORE_HEADERS })
    }
}
