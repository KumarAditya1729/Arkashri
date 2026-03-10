'use client'

import { useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useAuditStore } from '../../store/auditStore'
import { Button } from '@/components/ui/button'
import { MessageSquare, AlertCircle, CheckCircle2 } from 'lucide-react'

interface ThreadedCommentaryProps {
    targetId: string
    targetType: 'Risk' | 'Phase' | 'Finding'
}

export function ThreadedCommentary({ targetId, targetType }: ThreadedCommentaryProps) {
    const [newComment, setNewComment] = useState('')
    const [isCritical, setIsCritical] = useState(false)
    // useShallow prevents infinite loop: filter() returns a new array every render.
    // useShallow does shallow equality on the result, so React won't re-render unless contents change.
    const notes = useAuditStore(useShallow((state) => state.notes.filter(n => n.targetId === targetId)))
    const addNote = useAuditStore((state) => state.addNote)
    const resolveNote = useAuditStore((state) => state.resolveNote)

    const handleAddNote = () => {
        if (!newComment.trim()) return

        addNote({
            id: `NOTE-${Math.floor(Math.random() * 10000)}`,
            targetId,
            targetType,
            content: newComment,
            author: 'Current Auditor',
            timestamp: new Date().toISOString(),
            isCritical,
            resolved: false
        })
        setNewComment('')
        setIsCritical(false)
    }

    return (
        <div className="bg-slate-50 border rounded-md p-4 mt-4">
            <h4 className="flex items-center text-sm font-semibold text-gray-700 mb-3">
                <MessageSquare className="w-4 h-4 mr-2" />
                Review Notes & Commentary
            </h4>

            {notes.length > 0 && (
                <div className="space-y-3 mb-4">
                    {notes.map(note => (
                        <div key={note.id} className={`p-3 rounded-md text-sm ${note.isCritical && !note.resolved ? 'bg-red-50 border border-red-100' : 'bg-white border'}`}>
                            <div className="flex justify-between items-start mb-1">
                                <span className="font-semibold text-gray-800">{note.author}</span>
                                <span className="text-xs text-gray-400">{new Date(note.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <p className="text-gray-700 mb-2">{note.content}</p>
                            <div className="flex justify-between items-center">
                                {note.isCritical && (
                                    <span className="flex items-center text-xs font-semibold text-red-600">
                                        <AlertCircle className="w-3 h-3 mr-1" /> Critical Finding
                                    </span>
                                )}
                                {!note.isCritical && <span></span>}
                                {note.isCritical && !note.resolved && (
                                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => resolveNote(note.id)}>
                                        <CheckCircle2 className="w-3 h-3 mr-1" /> Resolve
                                    </Button>
                                )}
                                {note.resolved && (
                                    <span className="flex items-center text-xs font-semibold text-green-600">
                                        <CheckCircle2 className="w-3 h-3 mr-1" /> Resolved
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <div className="flex flex-col gap-2">
                <textarea
                    className="w-full text-sm p-2 border rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[60px]"
                    placeholder="Add a review note..."
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                />
                <div className="flex justify-between items-center">
                    <label className="flex items-center text-sm text-gray-600 cursor-pointer">
                        <input
                            type="checkbox"
                            className="mr-2 rounded text-blue-600"
                            checked={isCritical}
                            onChange={(e) => setIsCritical(e.target.checked)}
                        />
                        Mark as Critical Blocking Issue
                    </label>
                    <Button size="sm" onClick={handleAddNote} disabled={!newComment.trim()}>
                        Post Note
                    </Button>
                </div>
            </div>
        </div>
    )
}
