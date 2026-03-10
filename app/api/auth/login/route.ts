import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function POST(request: Request) {
    try {
        const body = await request.json()
        const { email, password } = body

        const res = await fetch(`${BACKEND_URL}/api/v1/token/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        })

        if (!res.ok) {
            const error = await res.text()
            return NextResponse.json({ error }, { status: res.status })
        }

        const data = await res.json()
        const { access_token } = data

        // Set HttpOnly cookie
        const cookieStore = await cookies()
        cookieStore.set('arkashri_token', access_token, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'strict',
            path: '/',
            maxAge: 60 * 60 * 24, // 24 hours
        })

        return NextResponse.json(data)
    } catch (error) {
        console.error('Auth proxy error:', error)
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 })
    }
}
