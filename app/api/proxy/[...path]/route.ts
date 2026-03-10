import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

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
    const targetUrl = `${BACKEND_URL}/api/${path}${searchParams}`

    const cookieStore = await cookies()
    const token = cookieStore.get('arkashri_token')?.value

    const headers = new Headers(request.headers)
    headers.delete('host')
    headers.delete('connection')
    if (token) {
        headers.set('Authorization', `Bearer ${token}`)
    }

    try {
        const body = request.method !== 'GET' ? await request.arrayBuffer() : undefined

        const res = await fetch(targetUrl, {
            method: request.method,
            headers,
            body,
            // Skip cache in dev/production to ensure fresh audit data
            cache: 'no-store',
        })

        const resBody = await res.arrayBuffer()
        const responseHeaders = new Headers(res.headers)
        // Remove headers that might cause issues when proxied
        responseHeaders.delete('content-encoding')
        responseHeaders.delete('transfer-encoding')

        return new Response(resBody, {
            status: res.status,
            statusText: res.statusText,
            headers: responseHeaders,
        })
    } catch (error) {
        console.error(`Proxy error for ${targetUrl}:`, error)
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 })
    }
}
