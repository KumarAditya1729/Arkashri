import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

import { clearAuthCookies, applyAuthCookies } from '@/lib/auth/cookies'
import { readAuthCookies, resolveServerAuth } from '@/lib/auth/server'

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' }

export async function GET() {
    try {
        const cookieStore = await cookies()
        const auth = await resolveServerAuth(readAuthCookies(cookieStore))

        if (!auth.session) {
            const response = NextResponse.json({ error: 'Not authenticated' }, { status: 401, headers: NO_STORE_HEADERS })
            if (auth.clearCookies) {
                clearAuthCookies(response)
            }
            return response
        }

        const response = NextResponse.json(auth.session, {
            headers: NO_STORE_HEADERS,
        })

        if (auth.refreshedTokens) {
            applyAuthCookies(response, auth.refreshedTokens)
        }

        return response
    } catch (error) {
        console.error('Session resolution error:', error)
        return NextResponse.json(
            { error: 'Authentication service unavailable' },
            { status: 503, headers: NO_STORE_HEADERS },
        )
    }
}
