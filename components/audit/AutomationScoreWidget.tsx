'use client'

import { useEffect, useRef, useState } from 'react'
import { AutomationDimension } from '@/lib/api'

// ─── SVG Circular Gauge ───────────────────────────────────────────────────────

function CircularGauge({ score, grade }: { score: number; grade: string }) {
    const [animated, setAnimated] = useState(0)
    const animRef = useRef<number | null>(null)

    useEffect(() => {
        const target = score
        const start = performance.now()
        const duration = 1800  // ms

        const tick = (now: number) => {
            const t = Math.min((now - start) / duration, 1)
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - t, 3)
            setAnimated(eased * target)
            if (t < 1) animRef.current = requestAnimationFrame(tick)
        }
        animRef.current = requestAnimationFrame(tick)
        return () => { if (animRef.current) cancelAnimationFrame(animRef.current) }
    }, [score])

    const radius = 80
    const stroke = 12
    const cx = 100
    const cy = 100
    const circumference = 2 * Math.PI * radius
    // Gauge arc: 270° sweep starting from -225° (bottom-left), ending at 45° (bottom-right)
    const arcStart = -225 * (Math.PI / 180)
    const arcTotal = 270 * (Math.PI / 180)
    const progress = (animated / 100) * arcTotal

    // Convert polar to cartesian
    const polar = (angle: number) => ({
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
    })

    const start = polar(arcStart)
    const bgEnd = polar(arcStart + arcTotal)
    const pgEnd = polar(arcStart + progress)

    const bgArcFlag = arcTotal > Math.PI ? 1 : 0
    const fgArcFlag = progress > Math.PI ? 1 : 0

    const gradeColor =
        grade === 'A+' ? '#10b981' :
            grade === 'A' ? '#22c55e' :
                grade === 'A−' ? '#84cc16' :
                    grade === 'B+' ? '#f59e0b' :
                        grade === 'B' ? '#f97316' : '#ef4444'

    const trackColor = '#e5e7eb'

    return (
        <svg viewBox="0 0 200 180" className="w-48 h-44 mx-auto">
            {/* Gradient definition */}
            <defs>
                <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#3b82f6" />
                    <stop offset="60%" stopColor="#22c55e" />
                    <stop offset="100%" stopColor="#10b981" />
                </linearGradient>
                <filter id="glow">
                    <feGaussianBlur stdDeviation="2" result="coloredBlur" />
                    <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
            </defs>

            {/* Background track */}
            <path
                d={`M ${start.x} ${start.y} A ${radius} ${radius} 0 ${bgArcFlag} 1 ${bgEnd.x} ${bgEnd.y}`}
                fill="none" stroke={trackColor} strokeWidth={stroke} strokeLinecap="round"
            />

            {/* Progress arc */}
            {animated > 0.5 && (
                <path
                    d={`M ${start.x} ${start.y} A ${radius} ${radius} 0 ${fgArcFlag} 1 ${pgEnd.x} ${pgEnd.y}`}
                    fill="none" stroke="url(#gaugeGradient)" strokeWidth={stroke} strokeLinecap="round"
                    filter="url(#glow)"
                />
            )}

            {/* Centre score text */}
            <text x={cx} y={cy - 6} textAnchor="middle" fontSize="28" fontWeight="900"
                fill={gradeColor} fontFamily="system-ui, sans-serif">
                {animated.toFixed(1)}
            </text>
            <text x={cx} y={cy + 12} textAnchor="middle" fontSize="11" fill="#6b7280" fontFamily="system-ui, sans-serif">
                AUTOMATION
            </text>

            {/* Grade badge */}
            <rect x={cx - 16} y={cy + 22} width={32} height={18} rx={9} fill={gradeColor} />
            <text x={cx} y={cy + 35} textAnchor="middle" fontSize="11" fontWeight="800"
                fill="white" fontFamily="system-ui, sans-serif">
                {grade}
            </text>

            {/* Tick marks at 0%, 50%, 90%, 100% */}
            {[0, 50, 90, 100].map(pct => {
                const angle = arcStart + (pct / 100) * arcTotal
                const inner = { x: cx + (radius - stroke - 4) * Math.cos(angle), y: cy + (radius - stroke - 4) * Math.sin(angle) }
                const outer = { x: cx + (radius + 4) * Math.cos(angle), y: cy + (radius + 4) * Math.sin(angle) }
                return (
                    <line key={pct} x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y}
                        stroke={pct <= animated ? gradeColor : '#d1d5db'} strokeWidth="1.5" />
                )
            })}

            {/* 90% threshold label */}
            {(() => {
                const angle = arcStart + (90 / 100) * arcTotal
                const lx = cx + (radius + 16) * Math.cos(angle)
                const ly = cy + (radius + 16) * Math.sin(angle)
                return <text x={lx} y={ly} textAnchor="middle" fontSize="8" fill="#9ca3af">90%</text>
            })()}
        </svg>
    )
}

// ─── Dimension Bar ────────────────────────────────────────────────────────────

function DimensionBar({ dim }: { dim: AutomationDimension }) {
    const [width, setWidth] = useState(0)

    useEffect(() => {
        const t = setTimeout(() => setWidth(dim.score), 300)
        return () => clearTimeout(t)
    }, [dim.score])

    const color = dim.score >= 95 ? 'bg-emerald-500' : dim.score >= 90 ? 'bg-green-500' : dim.score >= 85 ? 'bg-lime-500' : 'bg-amber-400'

    return (
        <div className="flex items-center gap-3">
            <div className="w-36 text-xs font-semibold text-gray-700 leading-tight truncate">{dim.label}</div>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-1000 ease-out ${color}`}
                    style={{ width: `${width}%` }} />
            </div>
            <div className="w-10 text-right text-xs font-bold text-gray-600">{dim.score.toFixed(0)}%</div>
        </div>
    )
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface AutomationScoreWidgetProps {
    score: number
    grade: string
    insight: string
    dimensions: AutomationDimension[]
    isLive: boolean
}

export function AutomationScoreWidget({ score, grade, insight, dimensions, isLive }: AutomationScoreWidgetProps) {
    return (
        <div className="bg-gradient-to-br from-[#001a54] via-[#002776] to-[#0040a0] rounded-2xl p-6 text-white shadow-xl shadow-blue-900/30 col-span-2 flex gap-6">
            {/* Gauge Side */}
            <div className="flex-shrink-0 flex flex-col items-center justify-center">
                <CircularGauge score={score} grade={grade} />
                <div className="flex items-center gap-1.5 mt-1">
                    {isLive ? (
                        <span className="flex items-center gap-1 text-xs font-semibold text-emerald-300">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            LIVE
                        </span>
                    ) : (
                        <span className="text-xs text-blue-300 font-medium">MODELLED</span>
                    )}
                    <span className="text-blue-400 text-xs">·</span>
                    <span className="text-xs text-blue-300">Arkashri Engine</span>
                </div>
            </div>

            {/* Data Side */}
            <div className="flex-1 min-w-0">
                <div className="mb-1">
                    <div className="text-xs font-semibold text-blue-300 uppercase tracking-widest mb-0.5">Audit Automation Index</div>
                    <h3 className="text-xl font-black leading-tight">
                        {score >= 90
                            ? '✓ Enterprise Threshold Exceeded'
                            : 'Approaching Enterprise Threshold'}
                    </h3>
                </div>

                <p className="text-blue-200 text-xs leading-relaxed mb-4 line-clamp-2">{insight}</p>

                {/* Dimension bars */}
                <div className="space-y-2">
                    {dimensions.map(d => (
                        <DimensionBar key={d.label} dim={d} />
                    ))}
                </div>

                {/* Threshold marker */}
                <div className="mt-4 flex items-center gap-2 bg-white/10 rounded-lg px-3 py-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
                    <span className="text-xs text-blue-200">
                        Industry benchmark: <strong className="text-white">≥ 90%</strong> for enterprise audit automation
                        {score >= 90 ? <span className="text-emerald-300"> — Achieved ✓</span> : ''}
                    </span>
                </div>
            </div>
        </div>
    )
}
