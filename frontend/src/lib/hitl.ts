/** HITL H3 helpers — display/permission only; backend remains authoritative. */

import type { Task } from '../types/task'

export const STATUS_AWAITING_APPROVAL = 'awaiting_approval'

export function isActiveRunStatus(status: string): boolean {
  return status === 'pending' || status === 'running' || status === STATUS_AWAITING_APPROVAL
}

export function isAwaitingApproval(status: string): boolean {
  return status === STATUS_AWAITING_APPROVAL
}

/** Mirror RUN_CANCEL: creator or workspace owner. Backend still enforces. */
export function canActOnHitl(
  task: Task,
  userId: string | null | undefined,
  role: string | null | undefined,
): boolean {
  if (!isAwaitingApproval(task.status)) return false
  if (task.hitl_resume_requested) return false
  if (!userId) return false
  if (task.user_id === userId) return true
  return role === 'owner'
}

export type HitlContext = {
  sql: string | null
  sqlSnapshot: string | null
  sqlSha256: string | null
  phase: string | null
  note: string | null
}

export function extractHitlContext(
  resultJson: Record<string, unknown> | null | undefined,
): HitlContext {
  const empty: HitlContext = {
    sql: null,
    sqlSnapshot: null,
    sqlSha256: null,
    phase: null,
    note: null,
  }
  if (!resultJson || typeof resultJson !== 'object') return empty

  const topSql = typeof resultJson.sql === 'string' ? resultJson.sql : null
  const platform = resultJson.platform
  if (!platform || typeof platform !== 'object') {
    return { ...empty, sql: topSql }
  }
  const hitl = (platform as Record<string, unknown>).hitl
  if (!hitl || typeof hitl !== 'object') {
    return { ...empty, sql: topSql }
  }
  const h = hitl as Record<string, unknown>
  const sqlSnapshot = typeof h.sql_snapshot === 'string' ? h.sql_snapshot : null
  const sqlFromHitl = typeof h.sql === 'string' ? h.sql : null
  return {
    sql: sqlSnapshot || sqlFromHitl || topSql,
    sqlSnapshot,
    sqlSha256: typeof h.sql_sha256 === 'string' ? h.sql_sha256 : null,
    phase: typeof h.phase === 'string' ? h.phase : null,
    note: typeof h.note === 'string' ? h.note : null,
  }
}

export function isHitlDisabledError(err: { status?: number; message?: string }): boolean {
  if (err.status !== 409) return false
  const msg = (err.message || '').toLowerCase()
  return msg.includes('hitl') && msg.includes('disabled')
}
