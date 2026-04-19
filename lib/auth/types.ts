export type UserRole = 'admin' | 'operator' | 'reviewer' | 'read_only'

export interface AuthUser {
    id: string
    fullName: string
    email: string
    role: UserRole
    tenantId: string
    organisation: string
    avatarInitials: string
}

export interface AuthSession {
    user: AuthUser
}

export interface BackendAuthUser {
    id: string
    email: string
    full_name: string
    role: string
    tenant_id: string
    initials: string
}

export interface BackendAuthResponse {
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
    user: BackendAuthUser
}

export interface VerifyTokenResponse {
    valid: true
    exp: number
    user: BackendAuthUser
}

export interface RegisterPayload {
    fullName: string
    email: string
    password: string
    organisation: string
    role: string
}

export interface WebSocketTicketResponse {
    ticket: string
    tenant_id: string
    jurisdiction: string
    expires_in: number
}

