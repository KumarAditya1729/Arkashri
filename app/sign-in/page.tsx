'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '../../store/authStore'
import { Eye, EyeOff, Shield, Loader2, AlertCircle } from 'lucide-react'

// Frontend auth falls through to backend router

export default function SignInPage() {
    const router = useRouter()
    const loginWithBackend = useAuthStore((s) => s.loginWithBackend)

    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setLoading(true)

        try {
            await loginWithBackend(email.trim().toLowerCase(), password, {
                id: crypto.randomUUID(),
                fullName: email.split('@')[0],
                email: email.trim().toLowerCase(),
                role: 'auditor',
                organisation: 'Arkashri Systems',
                avatarInitials: email.substring(0, 2).toUpperCase(),
            })
            router.push('/dashboard')
        } catch {
            setError('Authentication failed. Please check your credentials and backend connection.')
        }
        setLoading(false)
    }

    return (
        <div className="min-h-screen bg-[#001a54] flex">
            {/* Left panel — branding */}
            <div className="hidden lg:flex flex-col justify-between w-[45%] bg-gradient-to-br from-[#001a54] via-[#002776] to-[#003d99] p-12 relative overflow-hidden">
                {/* Background geometric pattern */}
                <div className="absolute inset-0 opacity-10">
                    <div className="absolute top-20 left-20 w-64 h-64 border border-white/30 rounded-full" />
                    <div className="absolute top-32 left-32 w-48 h-48 border border-white/20 rounded-full" />
                    <div className="absolute bottom-32 right-16 w-80 h-80 border border-white/20 rounded-full" />
                    <div className="absolute bottom-48 right-32 w-56 h-56 border border-white/10 rounded-full" />
                </div>

                <div className="relative">
                    <div className="flex items-center gap-3 mb-16">
                        <div className="w-10 h-10 bg-white/10 rounded-xl flex items-center justify-center backdrop-blur-sm border border-white/20">
                            <Shield className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <div className="text-white font-bold text-xl tracking-tight">Arkashri</div>
                            <div className="text-blue-300 text-xs uppercase tracking-wider">Universal Audit Platform</div>
                        </div>
                    </div>

                    <h2 className="text-4xl font-black text-white leading-tight mb-4">
                        Infrastructure-Grade<br />
                        <span className="text-blue-300">Financial Intelligence</span>
                    </h2>
                    <p className="text-blue-200 text-base leading-relaxed max-w-sm">
                        Deterministic, multi-tenant, legally reconstructible audit command surface for enterprise assurance teams.
                    </p>
                </div>

                <div className="relative space-y-4">
                    {[
                        { label: 'SOC 2 Type II', detail: 'Certified infrastructure' },
                        { label: 'PCAOB AS 2110', detail: 'Regulatory binding' },
                        { label: 'ISA 315 (Revised 2019)', detail: 'Risk-based audit approach' },
                    ].map((item) => (
                        <div key={item.label} className="flex items-center gap-3">
                            <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0" />
                            <div>
                                <span className="text-white text-sm font-semibold">{item.label}</span>
                                <span className="text-blue-300 text-sm"> — {item.detail}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Right panel — form */}
            <div className="flex-1 flex items-center justify-center p-6 bg-gray-50">
                <div className="w-full max-w-md">
                    {/* Mobile logo */}
                    <div className="lg:hidden flex items-center gap-3 mb-10 justify-center">
                        <Shield className="w-8 h-8 text-[#002776]" />
                        <span className="text-xl font-black text-[#002776]">Arkashri</span>
                    </div>

                    <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
                        <div className="mb-8">
                            <h1 className="text-2xl font-black text-gray-900 tracking-tight">Welcome back</h1>
                            <p className="text-gray-500 text-sm mt-1">Sign in to your audit workspace</p>
                        </div>

                        {error && (
                            <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3 mb-6">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                                    Work Email
                                </label>
                                <input
                                    id="email"
                                    type="email"
                                    autoComplete="email"
                                    required
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="you@organisation.com"
                                    className="w-full h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                />
                            </div>

                            <div>
                                <div className="flex justify-between items-center mb-1.5">
                                    <label className="block text-sm font-semibold text-gray-700">
                                        Password
                                    </label>
                                    <button onClick={() => console.log('Forgot password clicked')} type="button" className="text-xs text-[#002776] font-medium hover:underline">
                                        Forgot password?
                                    </button>
                                </div>
                                <div className="relative">
                                    <input
                                        id="password"
                                        type={showPassword ? 'text' : 'password'}
                                        autoComplete="current-password"
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="w-full h-11 px-4 pr-10 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-3 top-3 text-gray-400 hover:text-gray-600"
                                    >
                                        {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                    </button>
                                </div>
                            </div>

                            <button
                                id="sign-in-btn"
                                type="submit"
                                disabled={loading}
                                className="w-full h-11 bg-[#002776] hover:bg-[#001a54] text-white font-semibold rounded-lg text-sm transition-all flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
                            >
                                {loading ? (
                                    <><Loader2 className="w-4 h-4 animate-spin" /> Authenticating…</>
                                ) : 'Sign In to Workspace'}
                            </button>
                        </form>

                        <div className="mt-6 pt-6 border-t border-gray-100">
                            <p className="text-center text-sm text-gray-500">
                                New to Arkashri?{' '}
                                <Link href="/register" className="text-[#002776] font-semibold hover:underline">
                                    Create an account
                                </Link>
                            </p>
                        </div>


                    </div>
                </div>
            </div>
        </div>
    )
}
