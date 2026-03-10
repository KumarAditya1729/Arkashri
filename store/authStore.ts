'use client'

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { signIn as apiSignIn, clearAuth } from '@/lib/api'

export type UserRole = 'admin' | 'operator' | 'reviewer' | 'auditor'

export interface AuthUser {
    id: string
    fullName: string
    email: string
    role: UserRole
    organisation: string
    avatarInitials: string
}

interface AuthState {
    user: AuthUser | null
    isAuthenticated: boolean
    backendLinked: boolean   // true when a real API token was issued
    login: (user: AuthUser) => void
    loginWithBackend: (email: string, password: string, fallbackUser: AuthUser) => Promise<void>
    logout: () => void
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set) => ({
            user: null,
            isAuthenticated: false,
            backendLinked: false,
            login: (user) => set({ user, isAuthenticated: true, backendLinked: false }),
            loginWithBackend: async (email, password, fallbackUser) => {
                try {
                    const res = await apiSignIn(email, password)
                    // Token is set automatically via HttpOnly cookie in /api/auth/login
                    set({
                        isAuthenticated: true,
                        backendLinked: true,
                        user: {
                            id: res.user.email,
                            fullName: res.user.full_name,
                            email: res.user.email,
                            role: res.user.role as UserRole,
                            organisation: 'Arkashri Systems',
                            avatarInitials: res.user.initials,
                        },
                    })
                } catch {
                    // Backend unreachable — fall back to local auth, don't block login
                    set({ user: fallbackUser, isAuthenticated: true, backendLinked: false })
                }
            },
            logout: () => {
                clearAuth()
                set({ user: null, isAuthenticated: false, backendLinked: false })
            },
        }),
        { name: 'arkashri-auth' }
    )
)
