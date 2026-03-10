/**
 * Engagement Registry — bridges frontend short display IDs to backend UUIDs.
 *
 * Short IDs are used in the UI for readability; the backend stores UUID4s.
 * Run scripts/seed_engagements.py to seed the backend and update the uuid field
 * once the backend is live. Until then, uuid is null → falls back to local mock data.
 */

export interface EngagementMeta {
    shortId: string
    uuid: string | null     // null = not yet seeded to backend
    auditType: string
    client: string
    jurisdiction: string
    period: string
}

// To generate real UUIDs, run: python3 scripts/seed_engagements.py
// Then paste the returned uuid values here.
export const ENGAGEMENT_REGISTRY: EngagementMeta[] = []

/** Map shortId → registry entry */
const _byShortId = new Map(ENGAGEMENT_REGISTRY.map(e => [e.shortId, e]))
/** Map uuid → registry entry */
const _byUuid = new Map(ENGAGEMENT_REGISTRY.filter(e => e.uuid).map(e => [e.uuid!, e]))

export function registryByShortId(shortId: string): EngagementMeta | undefined {
    return _byShortId.get(shortId)
}

export function registryByUuid(uuid: string): EngagementMeta | undefined {
    return _byUuid.get(uuid)
}

/** Returns the backend UUID for a given shortId, or null if not yet seeded. */
export function getUuid(shortId: string): string | null {
    return _byShortId.get(shortId)?.uuid ?? null
}
