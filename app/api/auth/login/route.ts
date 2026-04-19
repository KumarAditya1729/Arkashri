import { NextResponse } from 'next/server'

import { applyAuthCookies } from '@/lib/auth/cookies'
import { AuthApiError, buildAuthSession, requestTokenPair } from '@/lib/auth/shared'

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' }

export async function POST(request: Request) {
    try {
        const body = await request.json()
        const tokens = await requestTokenPair(body.email, body.password)

        const response = NextResponse.json(buildAuthSession(tokens.user), {
            headers: NO_STORE_HEADERS,
        })
        applyAuthCookies(response, tokens)

        return response
    } catch (error) {
        if (error instanceof AuthApiError) {
            return NextResponse.json({ error: error.message }, { status: error.status, headers: NO_STORE_HEADERS })
        }

        console.error('Auth proxy error:', error)
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500, headers: NO_STORE_HEADERS })
    }
}
