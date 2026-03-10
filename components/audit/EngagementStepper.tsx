'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Check, ChevronRight } from 'lucide-react'

interface Step {
    name: string
    path: string
}

const STEPS: Step[] = [
    { name: 'Planning', path: 'planning' },
    { name: 'Risks', path: 'risks' },
    { name: 'Controls', path: 'controls' },
    { name: 'Evidence', path: 'evidence' },
    { name: 'Testing', path: 'testing' },
    { name: 'Review', path: 'review' },
    { name: 'Report', path: 'report' },
]

export function EngagementStepper({ engagementId }: { engagementId: string }) {
    const pathname = usePathname()

    // Determine current index
    const currentIndex = STEPS.findIndex(step => pathname.includes(`/${step.path}`))

    // If we're on the root engagement page, we might not have a "step" path yet, 
    // or we might want to default to index -1 or 0.
    const effectiveIndex = currentIndex === -1 ? 0 : currentIndex

    return (
        <nav className="mb-8" aria-label="Progress">
            <ol role="list" className="flex items-center justify-between w-full">
                {STEPS.map((step, index) => {
                    const isCompleted = index < effectiveIndex
                    const isActive = index === effectiveIndex
                    const isUpcoming = index > effectiveIndex
                    const href = `/engagement/${engagementId}/${step.path}`

                    return (
                        <li key={step.name} className="relative flex-1">
                            {index !== 0 && (
                                <div className="absolute inset-0 flex items-center -left-1/2" aria-hidden="true">
                                    <div className={`h-0.5 w-full ${isCompleted || isActive ? 'bg-[#002776]' : 'bg-gray-200'}`} />
                                </div>
                            )}

                            <Link
                                href={href}
                                className="group relative flex flex-col items-center justify-center focus:outline-none"
                            >
                                <span className="flex items-center h-9" aria-hidden="true">
                                    {isCompleted ? (
                                        <span className="relative z-10 w-8 h-8 flex items-center justify-center bg-[#002776] rounded-full group-hover:bg-[#001a54] transition-colors shadow-sm">
                                            <Check className="w-5 h-5 text-white" aria-hidden="true" />
                                        </span>
                                    ) : isActive ? (
                                        <span className="relative z-10 w-8 h-8 flex items-center justify-center bg-white border-2 border-[#002776] rounded-full shadow-md">
                                            <span className="h-2.5 w-2.5 bg-[#002776] rounded-full animate-pulse" />
                                        </span>
                                    ) : (
                                        <span className="relative z-10 w-8 h-8 flex items-center justify-center bg-white border-2 border-gray-200 rounded-full group-hover:border-gray-300 transition-colors">
                                            <span className="h-2.5 w-2.5 bg-transparent rounded-full group-hover:bg-gray-200" />
                                        </span>
                                    )}
                                </span>
                                <span className={`mt-2 text-[10px] font-bold uppercase tracking-widest min-w-max transition-colors ${isActive ? 'text-[#002776]' : isCompleted ? 'text-gray-900' : 'text-gray-400 group-hover:text-gray-500'}`}>
                                    {step.name}
                                </span>
                            </Link>
                        </li>
                    )
                })}
            </ol>
        </nav>
    )
}
