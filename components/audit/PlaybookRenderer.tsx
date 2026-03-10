'use client'

import { moduleRegistry } from '@/lib/moduleRegistry'

interface PlaybookRendererProps {
    playbook: {
        auditType: string
        modules: { type: string }[]
    }
}

export function PlaybookRenderer({ playbook }: PlaybookRendererProps) {
    return (
        <div className="flex flex-col gap-6">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h2 className="text-xl font-semibold text-[#002776] mb-2">{playbook.auditType} Architecture</h2>
                <p className="text-sm text-gray-600">
                    This engagement is driven by a deterministic backend playbook. Modules are loaded dynamically based on registered schemas.
                </p>
            </div>

            <div className="flex flex-col gap-8">
                {playbook.modules.map((mod, index) => {
                    const ModuleComponent = moduleRegistry[mod.type]
                    if (!ModuleComponent) {
                        return (
                            <div key={index} className="p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                                Failed to load module: <strong>{mod.type}</strong>. Not found in moduleRegistry.
                            </div>
                        )
                    }

                    return (
                        <div key={index} className="module-wrapper">
                            <ModuleComponent />
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
