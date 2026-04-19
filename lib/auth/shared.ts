import { TENANT_HEADER_NAME } from './constants'
import type {
    AuthSession,
    BackendAuthResponse,
    BackendAuthUser,
    RegisterPayload,
    VerifyTokenResponse,
    WebSocketTicketResponse,
} from './types'

export class AuthApiError extends Error {
    constructor(
        public status: number,
        message: string,
    ) {
        super(message)
        this.name = 'AuthApiError'
    }
}

export function getBackendBaseUrl(): string {
    let baseUrl = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

    if (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://')) {
        baseUrl = `https://${baseUrl}`
    }

    return baseUrl.replace(/\/+$/, '')
}

export function getWebSocketBaseUrl(): string {
    let baseUrl = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'

    if (!baseUrl.startsWith('ws://') && !baseUrl.startsWith('wss://')) {
        baseUrl = baseUrl.startsWith('https://')
            ? baseUrl.replace('https://', 'wss://')
            : baseUrl.replace('http://', 'ws://')
    }

    return baseUrl.replace(/\/+$/, '')
}

export function getDefaultTenant(): string {
    return process.env.NEXT_PUBLIC_API_TENANT ?? 'default_tenant'
}

async function readErrorMessage(response: Response): Promise<string> {
    const text = await response.text().catch(() => '')

    if (!text) {
        return response.statusText || 'Authentication request failed.'
    }

    try {
        const payload = JSON.parse(text) as { detail?: string; error?: string }
        return payload.detail ?? payload.error ?? text
    } catch {
        return text
    }
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        throw new AuthApiError(response.status, await readErrorMessage(response))
    }

    return response.json() as Promise<T>
}

async function postBackendJson<T>(path: string, body: unknown, headers?: HeadersInit): Promise<T> {
    const response = await fetch(`${getBackendBaseUrl()}${path}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers,
        },
        body: JSON.stringify(body),
        cache: 'no-store',
    })

    return parseJsonResponse<T>(response)
}

export async function requestTokenPair(email: string, password: string, tenantId = getDefaultTenant()): Promise<BackendAuthResponse> {
    return postBackendJson<BackendAuthResponse>(
        '/api/v1/token/',
        { email, password },
        { [TENANT_HEADER_NAME]: tenantId },
    )
}

export async function requestRegistration(payload: RegisterPayload): Promise<BackendAuthResponse> {
    return postBackendJson<BackendAuthResponse>('/api/v1/auth/register', {
        full_name: payload.fullName,
        email: payload.email,
        password: payload.password,
        organisation: payload.organisation,
        role: payload.role,
    })
}

export async function refreshTokenPair(refreshToken: string): Promise<BackendAuthResponse> {
    return postBackendJson<BackendAuthResponse>('/api/v1/token/refresh', {
        refresh_token: refreshToken,
    })
}

export async function revokeSession(tokens: { refreshToken?: string; accessToken?: string }): Promise<void> {
    if (!tokens.refreshToken && !tokens.accessToken) {
        return
    }

    const response = await fetch(`${getBackendBaseUrl()}/api/v1/token/logout`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(tokens.accessToken ? { Authorization: `Bearer ${tokens.accessToken}` } : {}),
        },
        body: JSON.stringify({ refresh_token: tokens.refreshToken ?? null }),
        cache: 'no-store',
    })

    if (!response.ok && response.status !== 204) {
        throw new AuthApiError(response.status, await readErrorMessage(response))
    }
}

export async function verifyAccessToken(accessToken: string): Promise<VerifyTokenResponse> {
    return postBackendJson<VerifyTokenResponse>('/api/v1/token/verify', {
        token: accessToken,
    })
}

export async function requestWebSocketTicket(accessToken: string, jurisdiction: string): Promise<WebSocketTicketResponse> {
    const response = await fetch(`${getBackendBaseUrl()}/api/v1/token/ws-ticket?jurisdiction=${encodeURIComponent(jurisdiction)}`, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${accessToken}`,
        },
        cache: 'no-store',
    })

    return parseJsonResponse<WebSocketTicketResponse>(response)
}

function normalizeRole(role: string): AuthSession['user']['role'] {
    switch (role.toUpperCase()) {
        case 'ADMIN':
            return 'admin'
        case 'OPERATOR':
            return 'operator'
        case 'REVIEWER':
            return 'reviewer'
        case 'READ_ONLY':
            return 'read_only'
        default:
            return 'reviewer'
    }
}

function humanizeTenant(tenantId: string): string {
    if (tenantId === 'default_tenant') {
        return 'Arkashri Systems'
    }

    return tenantId
        .split(/[_-]+/)
        .filter(Boolean)
        .map((part) => part[0]?.toUpperCase() + part.slice(1))
        .join(' ')
}

function deriveInitials(fullName: string, fallbackEmail: string): string {
    const initials = fullName
        .split(/\s+/)
        .filter(Boolean)
        .map((part) => part[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)

    if (initials) {
        return initials
    }

    return fallbackEmail.slice(0, 2).toUpperCase()
}

export function buildAuthSession(user: BackendAuthUser): AuthSession {
    return {
        user: {
            id: user.id,
            fullName: user.full_name,
            email: user.email,
            role: normalizeRole(user.role),
            tenantId: user.tenant_id,
            organisation: humanizeTenant(user.tenant_id),
            avatarInitials: user.initials || deriveInitials(user.full_name, user.email),
        },
    }
}
