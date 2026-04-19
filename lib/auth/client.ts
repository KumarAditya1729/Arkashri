'use client'

import { AUTH_SESSION_INVALID_EVENT } from './constants'
import { AuthApiError } from './shared'
import type { AuthSession, RegisterPayload, WebSocketTicketResponse } from './types'

async function readRouteError(response: Response): Promise<string> {
    const text = await response.text().catch(() => '')

    if (!text) {
        return response.statusText || 'Authentication request failed.'
    }

    try {
        const payload = JSON.parse(text) as { error?: string }
        return payload.error ?? text
    } catch {
        return text
    }
}

async function requestAuthRoute<T>(
    path: string,
    init?: RequestInit,
    options?: { emitUnauthorized?: boolean },
): Promise<T> {
    const response = await fetch(path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
    })

    if (!response.ok) {
        if (response.status === 401 && options?.emitUnauthorized && typeof window !== 'undefined') {
            window.dispatchEvent(new Event(AUTH_SESSION_INVALID_EVENT))
        }

        throw new AuthApiError(response.status, await readRouteError(response))
    }

    return response.json() as Promise<T>
}

export function signIn(email: string, password: string): Promise<AuthSession> {
    return requestAuthRoute<AuthSession>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    })
}

export function register(payload: RegisterPayload): Promise<AuthSession> {
    return requestAuthRoute<AuthSession>('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
}

export function getSession(): Promise<AuthSession> {
    return requestAuthRoute<AuthSession>('/api/auth/session', undefined, { emitUnauthorized: true })
}

export async function signOut(): Promise<void> {
    await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
    })
}

export function getWebSocketTicket(jurisdiction: string): Promise<WebSocketTicketResponse> {
    return requestAuthRoute<WebSocketTicketResponse>(`/api/auth/ws-ticket?jurisdiction=${encodeURIComponent(jurisdiction)}`, undefined, {
        emitUnauthorized: true,
    })
}
