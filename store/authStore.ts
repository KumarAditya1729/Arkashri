'use client'

import { create } from 'zustand'
import { getSession, signOut } from '@/lib/auth/client'
import { AuthApiError } from '@/lib/auth/shared'
import type { AuthSession, AuthUser } from '@/lib/auth/types'

interface AuthState {
    user: AuthUser | null
    status: 'loading' | 'authenticated' | 'unauthenticated'
    initialized: boolean
    initialize: (options?: { force?: boolean }) => Promise<void>
    setSession: (session: AuthSession) => void
    setUnauthenticated: () => void
    logout: () => Promise<void>
}

let initializePromise: Promise<void> | null = null

export const useAuthStore = create<AuthState>()((set, get) => ({
    user: null,
    status: 'loading',
    initialized: false,
    initialize: async ({ force = false } = {}) => {
        if (!force && get().initialized) {
            return
        }

        if (initializePromise) {
            return initializePromise
        }

        if (!get().initialized) {
            set({ status: 'loading' })
        }

        initializePromise = (async () => {
            try {
                const session = await getSession()
                set({
                    user: session.user,
                    status: 'authenticated',
                    initialized: true,
                })
            } catch (error) {
                if (error instanceof AuthApiError && error.status === 401) {
                    set({
                        user: null,
                        status: 'unauthenticated',
                        initialized: true,
                    })
                    return
                }

                set((state) => ({
                    user: state.user,
                    status: state.user ? 'authenticated' : 'unauthenticated',
                    initialized: true,
                }))
            } finally {
                initializePromise = null
            }
        })()

        return initializePromise
    },
    setSession: (session) => set({
        user: session.user,
        status: 'authenticated',
        initialized: true,
    }),
    setUnauthenticated: () => set({
        user: null,
        status: 'unauthenticated',
        initialized: true,
    }),
    logout: async () => {
        try {
            await signOut()
        } finally {
            set({
                user: null,
                status: 'unauthenticated',
                initialized: true,
            })
        }
    },
}))
