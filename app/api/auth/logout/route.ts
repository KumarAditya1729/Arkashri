import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'

import { clearAuthCookies } from '@/lib/auth/cookies'
import { ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME } from '@/lib/auth/constants'
import { revokeSession } from '@/lib/auth/shared'

export async function POST() {
    try {
        const cookieStore = await cookies()
        const refreshToken = cookieStore.get(REFRESH_COOKIE_NAME)?.value
        const accessToken = cookieStore.get(ACCESS_COOKIE_NAME)?.value

        await revokeSession({ refreshToken, accessToken })
    } catch (error) {
        console.error('Logout revoke error:', error)
    }

    const response = NextResponse.json(
        { message: 'Logged out successfully' },
        { headers: { 'Cache-Control': 'no-store' } },
    )
    clearAuthCookies(response)
    return response
}
