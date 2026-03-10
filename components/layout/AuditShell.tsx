import { AIBox } from '@/components/core/AIBox'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AuditShell({ children }: { children: React.ReactNode }) {
    return (
        <div className="min-h-screen bg-gray-100 flex flex-col font-sans text-slate-900">
            <Topbar />
            <div className="flex flex-1 overflow-hidden">
                <Sidebar />

                {/* Main Workspace Area */}
                <main className="flex-1 overflow-y-auto p-8 relative">
                    <div className="max-w-6xl mx-auto">
                        {children}
                    </div>
                </main>

                {/* Persistent Context Pane - Grounded AI */}
                <aside className="w-80 border-l bg-white h-[calc(100vh-3.5rem)] sticky top-14 hidden lg:block overflow-hidden shadow-sm">
                    <AIBox />
                </aside>
            </div>
        </div>
    )
}
