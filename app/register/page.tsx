'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '../../store/authStore'
import { Eye, EyeOff, Shield, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'

const ROLES = [
    { value: 'admin', label: 'Platform Administrator' },
    { value: 'operator', label: 'Audit Operator' },
    { value: 'auditor', label: 'Audit Professional' },
    { value: 'reviewer', label: 'Quality Reviewer' },
] as const

function PasswordStrength({ password }: { password: string }) {
    const checks = [
        { label: '8+ characters', ok: password.length >= 8 },
        { label: 'Uppercase letter', ok: /[A-Z]/.test(password) },
        { label: 'Number', ok: /\d/.test(password) },
        { label: 'Special character', ok: /[!@#$%^&*]/.test(password) },
    ]
    const score = checks.filter((c) => c.ok).length
    const colors = ['bg-red-400', 'bg-orange-400', 'bg-yellow-400', 'bg-green-500']
    if (!password) return null
    return (
        <div className="mt-2 space-y-2">
            <div className="flex gap-1">
                {[0, 1, 2, 3].map((i) => (
                    <div key={i} className={`h-1 flex-1 rounded-full transition-all ${i < score ? colors[score - 1] : 'bg-gray-200'}`} />
                ))}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
                {checks.map((c) => (
                    <span key={c.label} className={`flex items-center gap-1 text-xs ${c.ok ? 'text-green-600' : 'text-gray-400'}`}>
                        <CheckCircle2 className={`w-3 h-3 ${c.ok ? 'text-green-500' : 'text-gray-300'}`} />
                        {c.label}
                    </span>
                ))}
            </div>
        </div>
    )
}

export default function RegisterPage() {
    const router = useRouter()
    const login = useAuthStore((s) => s.login)

    const [form, setForm] = useState({ fullName: '', email: '', organisation: '', role: 'auditor', password: '', confirm: '' })
    const [showPassword, setShowPassword] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        setForm((f) => ({ ...f, [field]: e.target.value }))

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')

        if (form.password !== form.confirm) return setError('Passwords do not match.')
        if (form.password.length < 8) return setError('Password must be at least 8 characters.')

        setLoading(true)
        await new Promise((r) => setTimeout(r, 1000))

        login({
            id: crypto.randomUUID(),
            fullName: form.fullName,
            email: form.email.trim().toLowerCase(),
            role: form.role as any,
            organisation: form.organisation,
            avatarInitials: form.fullName.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2),
        })
        router.push('/dashboard')
        setLoading(false)
    }

    return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
            <div className="w-full max-w-lg">
                {/* Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center gap-2.5 mb-4">
                        <div className="w-10 h-10 bg-[#002776] rounded-xl flex items-center justify-center shadow-md">
                            <Shield className="w-5 h-5 text-white" />
                        </div>
                        <span className="text-2xl font-black text-[#002776] tracking-tight">Arkashri</span>
                    </div>
                    <h1 className="text-2xl font-black text-gray-900 tracking-tight">Create your account</h1>
                    <p className="text-gray-500 text-sm mt-1">Join the universal audit command surface</p>
                </div>

                <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
                    {error && (
                        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3 mb-6">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-2">
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Full Name</label>
                                <input
                                    id="fullName"
                                    type="text"
                                    required
                                    value={form.fullName}
                                    onChange={set('fullName')}
                                    placeholder="Jane Smith"
                                    className="w-full h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                />
                            </div>

                            <div className="col-span-2">
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Work Email</label>
                                <input
                                    id="register-email"
                                    type="email"
                                    required
                                    value={form.email}
                                    onChange={set('email')}
                                    placeholder="you@organisation.com"
                                    className="w-full h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Organisation</label>
                                <input
                                    id="organisation"
                                    type="text"
                                    required
                                    value={form.organisation}
                                    onChange={set('organisation')}
                                    placeholder="Firm name"
                                    className="w-full h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Role</label>
                                <select
                                    id="role"
                                    value={form.role}
                                    onChange={set('role')}
                                    className="w-full h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all"
                                >
                                    {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                                </select>
                            </div>

                            <div className="col-span-2">
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Password</label>
                                <div className="relative">
                                    <input
                                        id="register-password"
                                        type={showPassword ? 'text' : 'password'}
                                        required
                                        value={form.password}
                                        onChange={set('password')}
                                        placeholder="Create a strong password"
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
                                <PasswordStrength password={form.password} />
                            </div>

                            <div className="col-span-2">
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Confirm Password</label>
                                <input
                                    id="confirm-password"
                                    type="password"
                                    required
                                    value={form.confirm}
                                    onChange={set('confirm')}
                                    placeholder="Re-enter your password"
                                    className={`w-full h-11 px-4 rounded-lg border bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-[#002776]/30 focus:border-[#002776] transition-all ${form.confirm && form.confirm !== form.password ? 'border-red-300' : 'border-gray-200'}`}
                                />
                                {form.confirm && form.confirm !== form.password && (
                                    <p className="text-xs text-red-500 mt-1">Passwords do not match</p>
                                )}
                            </div>
                        </div>

                        <button
                            id="register-btn"
                            type="submit"
                            disabled={loading}
                            className="w-full h-11 mt-2 bg-[#002776] hover:bg-[#001a54] text-white font-semibold rounded-lg text-sm transition-all flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
                        >
                            {loading ? (
                                <><Loader2 className="w-4 h-4 animate-spin" /> Creating account…</>
                            ) : 'Create Account'}
                        </button>
                    </form>

                    <div className="mt-6 pt-5 border-t border-gray-100 text-center">
                        <p className="text-sm text-gray-500">
                            Already have an account?{' '}
                            <Link href="/sign-in" className="text-[#002776] font-semibold hover:underline">
                                Sign in
                            </Link>
                        </p>
                    </div>
                </div>

                <p className="text-center text-xs text-gray-400 mt-6">
                    By creating an account you agree to Arkashri's Terms of Service and Privacy Policy. Enterprise-grade security — all data encrypted at rest and in transit.
                </p>
            </div>
        </div>
    )
}
