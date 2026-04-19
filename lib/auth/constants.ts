export const ACCESS_COOKIE_NAME = 'arkashri_access_token'
export const REFRESH_COOKIE_NAME = 'arkashri_refresh_token'
export const LEGACY_AUTH_COOKIE_NAMES = ['arkashri_token']

export const ACCESS_TOKEN_MAX_AGE_SECONDS = 60 * 15
export const REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7

export const PUBLIC_ROUTES = ['/sign-in', '/register']
export const DEFAULT_AUTH_REDIRECT = '/dashboard'
export const DEFAULT_JURISDICTION = 'IN'
export const TENANT_HEADER_NAME = 'X-Arkashri-Tenant'

export const AUTH_SESSION_INVALID_EVENT = 'arkashri:auth-session-invalid'
