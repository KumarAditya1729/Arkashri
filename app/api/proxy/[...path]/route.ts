import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

import { applyAuthCookies, clearAuthCookies } from '@/lib/auth/cookies'
import { ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME } from '@/lib/auth/constants'
import { AuthApiError, getBackendBaseUrl, refreshTokenPair } from '@/lib/auth/shared'
import type { BackendAuthResponse } from '@/lib/auth/types'

const BACKEND_URL = getBackendBaseUrl()

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
    const { path } = await params
    return handleProxy(request, path.join('/'))
}

export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
    const { path } = await params
    return handleProxy(request, path.join('/'))
}

export async function PUT(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
    const { path } = await params
    return handleProxy(request, path.join('/'))
}

export async function PATCH(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
    const { path } = await params
    return handleProxy(request, path.join('/'))
}

export async function DELETE(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
    const { path } = await params
    return handleProxy(request, path.join('/'))
}

async function handleProxy(request: Request, path: string) {
    const searchParams = new URL(request.url).search
    const apiPath = path.startsWith('api/') ? path : `api/${path}`
    const targetUrl = `${BACKEND_URL.replace(/\/+$/, '')}/${apiPath}${searchParams}`

    const cookieStore = await cookies()
    const initialAccessToken = cookieStore.get(ACCESS_COOKIE_NAME)?.value
    const refreshToken = cookieStore.get(REFRESH_COOKIE_NAME)?.value

    const buildHeaders = (accessToken?: string) => {
        const headers = new Headers(request.headers)
        headers.delete('authorization')
        headers.delete('connection')
        headers.delete('content-length')
        headers.delete('cookie')
        headers.delete('host')

        if (accessToken) {
            headers.set('Authorization', `Bearer ${accessToken}`)
        }

        return headers
    }

    try {
        const requestBody = !['GET', 'HEAD'].includes(request.method) ? await request.arrayBuffer() : undefined

        const forward = async (accessToken?: string) => fetch(targetUrl, {
            method: request.method,
            headers: buildHeaders(accessToken),
            body: requestBody,
            cache: 'no-store',
        })

        let res = await forward(initialAccessToken)
        let refreshedTokens: BackendAuthResponse | null = null
        let shouldClearCookies = false
        let authRejected = res.status === 401 && !refreshToken

        if (res.status === 401 && refreshToken) {
            try {
                refreshedTokens = await refreshTokenPair(refreshToken)
                res = await forward(refreshedTokens.access_token)
                authRejected = res.status === 401
            } catch (error) {
                shouldClearCookies = error instanceof AuthApiError && error.status === 401
                authRejected = shouldClearCookies
            }
        }

        const resBody = await res.arrayBuffer()
        const responseHeaders = new Headers(res.headers)
        // Remove headers that might cause issues when proxied
        responseHeaders.delete('content-encoding')
        responseHeaders.delete('set-cookie')
        responseHeaders.delete('transfer-encoding')

        const response = new NextResponse(resBody, {
            status: res.status,
            statusText: res.statusText,
            headers: responseHeaders,
        })

        if (refreshedTokens) {
            applyAuthCookies(response, refreshedTokens)
        }

        if (shouldClearCookies || authRejected) {
            clearAuthCookies(response)
        }

        return response
    } catch (error) {
        console.error(`Proxy error for ${targetUrl}:`, error)
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 })
    }
}
