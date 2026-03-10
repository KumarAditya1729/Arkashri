'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Bell, Search, LogOut, ChevronDown } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/store/authStore'
import { useState } from 'react'

export function Topbar() {
    const { user, logout } = useAuthStore()
    const router = useRouter()
    const [showUserMenu, setShowUserMenu] = useState(false)

    const handleLogout = () => {
        logout()
        router.push('/sign-in')
    }

    return (
        <header className="h-14 border-b bg-[#002776] text-white flex items-center justify-between px-6 sticky top-0 z-50">
            <div className="flex items-center gap-4">
                <Link href="/dashboard" className="flex items-center gap-3 hover:opacity-90 transition-opacity">
                    <h1 className="font-bold tracking-tight">Arkashri</h1>
                    <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full uppercase">Universal Audit Platform</span>
                </Link>
            </div>

            <div className="flex-1 max-w-md mx-8 relative">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                <Input
                    placeholder="Global Search (Entities, Risks, Evidence)..."
                    className="h-9 pl-9 bg-white/10 border-white/20 text-white placeholder:text-gray-300 focus-visible:ring-offset-0 focus-visible:ring-1 focus-visible:ring-white"
                />
            </div>

            <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/10 hover:text-white" onClick={() => console.log('Notification clicked')}>
                    <Bell className="w-5 h-5" />
                </Button>

                {user ? (
                    <div className="relative ml-4 pl-4 border-l border-white/20">
                        <button
                            onClick={() => setShowUserMenu(!showUserMenu)}
                            className="flex items-center gap-2 hover:bg-white/10 rounded-lg px-2 py-1 transition-colors"
                        >
                            <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center text-sm font-bold border border-white/30">
                                {user.avatarInitials}
                            </div>
                            <div className="text-right hidden sm:block">
                                <div className="text-sm font-semibold leading-tight">{user.fullName}</div>
                                <div className="text-xs text-blue-200 capitalize">{user.role}</div>
                            </div>
                            <ChevronDown className="w-3.5 h-3.5 text-blue-200" />
                        </button>

                        {showUserMenu && (
                            <div className="absolute right-0 top-12 w-52 bg-white rounded-xl shadow-xl border border-gray-100 py-1 z-50">
                                <div className="px-4 py-3 border-b border-gray-50">
                                    <p className="text-sm font-semibold text-gray-900">{user.fullName}</p>
                                    <p className="text-xs text-gray-500 truncate">{user.email}</p>
                                    <p className="text-xs text-gray-400">{user.organisation}</p>
                                </div>
                                <button
                                    onClick={handleLogout}
                                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                                >
                                    <LogOut className="w-4 h-4" />
                                    Sign out
                                </button>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="ml-4 pl-4 border-l border-white/20 flex gap-2">
                        <Link href="/sign-in">
                            <Button variant="ghost" size="sm" className="text-white hover:bg-white/10 hover:text-white text-xs">
                                Sign In
                            </Button>
                        </Link>
                        <Link href="/register">
                            <Button size="sm" className="bg-white text-[#002776] hover:bg-blue-50 text-xs font-semibold">
                                Register
                            </Button>
                        </Link>
                    </div>
                )}
            </div>
        </header>
    )
}
