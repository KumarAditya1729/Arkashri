import { create } from 'zustand'

export type AuditStage = 'Dashboard' | 'Planning' | 'Risks' | 'Controls' | 'Testing' | 'Evidence' | 'Review' | 'Report'

export interface Risk {
    id: string
    title: string
    score: number
    description?: string
    status: 'Open' | 'Mitigated' | 'Accepted'
}

export interface Procedure {
    id: string
    name: string
    status: 'Pending' | 'In Progress' | 'Completed' | 'Review Required'
    riskId?: string
}

export interface Evidence {
    id: string
    filename: string
    hash: string
    uploadTime: string
    linkedProcedureId?: string
}

export interface ReviewNote {
    id: string
    targetId: string
    targetType: 'Risk' | 'Phase' | 'Finding'
    content: string
    author: string
    timestamp: string
    isCritical: boolean
    resolved: boolean
}

interface AuditState {
    engagementId: string | null
    auditType: string | null
    currentStage: AuditStage
    risks: Risk[]
    procedures: Procedure[]
    evidence: Evidence[]
    notes: ReviewNote[]
    reviewStatus: 'Not Started' | 'In Review' | 'Approved'

    // Actions
    setEngagement: (id: string, type: string) => void
    setStage: (stage: AuditStage) => void
    addRisk: (risk: Risk) => void
    updateRisk: (id: string, riskUpdate: Partial<Risk>) => void
    addProcedure: (procedure: Procedure) => void
    updateProcedure: (id: string, procedureUpdate: Partial<Procedure>) => void
    addEvidence: (evidence: Evidence) => void
    addNote: (note: ReviewNote) => void
    resolveNote: (noteId: string) => void
}

export const useAuditStore = create<AuditState>((set) => ({
    engagementId: null,
    auditType: null,
    currentStage: 'Dashboard',
    risks: [],
    procedures: [],
    evidence: [],
    notes: [],
    reviewStatus: 'Not Started',

    setEngagement: (id, type) => set({ engagementId: id, auditType: type }),
    setStage: (stage) => set({ currentStage: stage }),
    addRisk: (risk) => set((state) => ({ risks: [...state.risks, risk] })),
    updateRisk: (id, riskUpdate) =>
        set((state) => ({
            risks: state.risks.map((r) => (r.id === id ? { ...r, ...riskUpdate } : r)),
        })),
    addProcedure: (procedure) => set((state) => ({ procedures: [...state.procedures, procedure] })),
    updateProcedure: (id, procedureUpdate) =>
        set((state) => ({
            procedures: state.procedures.map((p) => (p.id === id ? { ...p, ...procedureUpdate } : p)),
        })),
    addEvidence: (evidence) => set((state) => ({ evidence: [...state.evidence, evidence] })),
    addNote: (note) => set((state) => ({ notes: [...state.notes, note] })),
    resolveNote: (noteId: string) =>
        set((state) => ({
            notes: state.notes.map((n) => (n.id === noteId ? { ...n, resolved: true } : n)),
        })),
}))
