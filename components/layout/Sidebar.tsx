'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Briefcase, FileSearch, ShieldAlert, CheckSquare, Microscope, Link as LinkIcon, FileCheck, Eye, ScrollText, Brain, Network, Activity, BarChart3, Database } from 'lucide-react'

const navItems = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/engagement-overview', label: 'Engagement Overview', icon: Briefcase },
    { href: '/planning', label: 'Planning', icon: FileSearch },
    { href: '/risks', label: 'Risks', icon: ShieldAlert },
    { href: '/controls', label: 'Controls', icon: CheckSquare },
    { href: '/testing', label: 'Testing', icon: Microscope },
    { href: '/evidence', label: 'Evidence', icon: LinkIcon },
    { href: '/review', label: 'Review', icon: Eye },
    { href: '/report', label: 'Report', icon: FileCheck },
    { href: '/regulatory-updates', label: 'Regulatory Updates', icon: ScrollText },
    { href: '/analytics', label: 'ML Analytics', icon: Brain },
    { href: '/blockchain', label: 'Multi-Chain Blockchain', icon: Network },
    { href: '/monitoring', label: 'Production Monitoring', icon: Activity },
]

export function Sidebar() {
    const pathname = usePathname()

    return (
        <aside className="w-64 border-r bg-slate-50 flex flex-col h-[calc(100vh-3.5rem)] sticky top-14 overflow-hidden">
            <div className="p-4 border-b">
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Workspace Navigation</div>
            </div>
            <nav className="flex-1 overflow-y-auto p-3 space-y-1">
                {navItems.map((item) => {
                    const Icon = item.icon
                    const isActive = pathname === item.href || (pathname.startsWith('/engagement') && item.href.includes('engagement'))
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? 'bg-[#e5f6ff] text-[#002776]' : 'text-gray-700 hover:bg-gray-200 hover:text-gray-900'
                                }`}
                        >
                            <Icon className={`w-4 h-4 ${isActive ? 'text-[#002776]' : 'text-gray-500'}`} />
                            {item.label}
                        </Link>
                    )
                })}
            </nav>
            <div className="p-4 border-t bg-gray-100">
                <div className="text-xs text-gray-500 text-center">Enterprise Edition v2.0.0 ✅</div>
            </div>
        </aside>
    )
}
