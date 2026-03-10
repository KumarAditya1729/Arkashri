'use client'

import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '@/store/authStore'

interface WebSocketContextType {
    isConnected: boolean
    lastEvent: any | null
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [isConnected, setIsConnected] = useState(false)
    const [lastEvent, setLastEvent] = useState<any | null>(null)
    const socketRef = useRef<WebSocket | null>(null)
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

    const user = useAuthStore((s) => s.user)
    const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

    const connect = () => {
        if (socketRef.current) {
            console.log('WebSocket already connected or connecting')
            return
        }
        
        if (!isAuthenticated || !user) {
            console.log('Cannot connect WebSocket: not authenticated or no user data')
            return
        }

        const tenantId = user.organisation === 'Arkashri Systems' ? 'default_tenant' : user.id
        const jurisdiction = 'IN' // Default to India for now, could be dynamic
        const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'}/ws/audit/${tenantId}/${jurisdiction}`

        console.log(`Connecting to WebSocket: ${wsUrl}`)
        console.log(`User authenticated: ${isAuthenticated}, User ID: ${user.id}`)
        
        try {
            const socket = new WebSocket(wsUrl)
            socketRef.current = socket

            // Set a connection timeout
            const connectionTimeout = setTimeout(() => {
                if (socket.readyState === WebSocket.CONNECTING) {
                    console.error('WebSocket connection timeout - falling back to polling')
                    setIsConnected(false)
                    socket.close()
                    // Start fallback polling mechanism
                    startPollingFallback()
                }
            }, 5000) // 5 second timeout

            socket.onopen = () => {
                console.log('WebSocket Connected')
                setIsConnected(true)
                clearTimeout(connectionTimeout)
                stopPollingFallback()
            }

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data)
                    setLastEvent(data)
                    console.log('WS Event:', data)
                } catch (err) {
                    console.error('Failed to parse WS message:', err)
                }
            }

            socket.onclose = (event) => {
                console.log('WebSocket Disconnected', event.code, event.reason)
                setIsConnected(false)
                socketRef.current = null
                clearTimeout(connectionTimeout)
                
                // Start fallback polling on disconnect
                if (event.code !== 1000) {
                    console.log('WebSocket disconnected - starting fallback polling')
                    startPollingFallback()
                }
            }

            socket.onerror = (err) => {
                console.error('WebSocket Error:', err)
                console.error('WebSocket State:', socket.readyState)
                console.error('WebSocket URL:', wsUrl)
                clearTimeout(connectionTimeout)
                
                // Start fallback polling on error
                console.log('WebSocket error - starting fallback polling')
                startPollingFallback()
                
                // Provide more user-friendly error messages
                if (socket.readyState === WebSocket.CLOSED) {
                    console.error('WebSocket connection failed - falling back to polling')
                } else if (socket.readyState === WebSocket.CLOSING) {
                    console.error('WebSocket connection is closing')
                }
                
                socket.close()
            }
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error)
            startPollingFallback()
        }
    }

    const startPollingFallback = () => {
        // Fallback polling mechanism for when WebSocket fails
        console.log('Starting polling fallback for real-time updates')
        // This would implement periodic API calls to get updates
        // For now, just log that we're using the fallback
    }

    const stopPollingFallback = () => {
        // Stop the polling fallback when WebSocket connects
        console.log('Stopping polling fallback - WebSocket connected')
    }

    useEffect(() => {
        if (isAuthenticated && user) {
            // Add a small delay to ensure authentication is fully processed
            const timeoutId = setTimeout(() => {
                connect();
            }, 1000);
            
            return () => {
                clearTimeout(timeoutId);
            };
        } else {
            if (socketRef.current) {
                socketRef.current.close();
            }
        }

        return () => {
            if (socketRef.current) {
                socketRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        }
    }, [isAuthenticated, user])

    return (
        <WebSocketContext.Provider value={{ isConnected, lastEvent }}>
            {children}
        </WebSocketContext.Provider>
    )
}

export function useWebSocket() {
    const context = useContext(WebSocketContext)
    if (context === undefined) {
        throw new Error('useWebSocket must be used within a WebSocketProvider')
    }
    return context
}
