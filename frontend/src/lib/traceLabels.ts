/** Display-only labels for Analyze explainability (E2). Not a Trace product model. */

export const NODE_LABELS: Record<string, string> = {
  load_context: 'Load context',
  link_schema: 'Schema linking',
  generate_sql: 'Generate SQL',
  validate_sql: 'Policy Gate',
  execute_sql: 'Execute SQL',
  summarize: 'Summarize',
  build_charts: 'Build charts',
  write_report: 'Write report',
  fail: 'Failed',
}

export const FAILURE_CLASS_LABELS: Record<string, string> = {
  policy_denied: 'Policy denied',
  skill_error: 'Skill error',
  connector_error: 'Connector error',
  budget_rejected: 'Budget limit',
  capacity_rejected: 'Capacity limit',
  enqueue_error: 'Queue error',
  enqueue_rejected: 'Queue full', // legacy alias
  cancelled: 'Cancelled',
  timed_out: 'Timed out',
  timeout: 'Timed out',
  runtime_reclaimed: 'Runtime reclaimed',
  hitl_rejected: 'Rejected (HITL)',
  hitl_snapshot_mismatch: 'SQL snapshot mismatch',
  internal_error: 'Internal error',
  unknown: 'Unknown failure',
}

export const STATUS_LABELS: Record<string, string> = {
  awaiting_approval: 'Awaiting approval',
  pending: 'Pending',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
  timed_out: 'Timed out',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status
}

export type SqlQuality = {
  schema_version?: number
  link_status?: string | null
  link_method?: string | null
  link_reason?: string | null
  selected_tables?: string[]
  selected_columns?: string[]
  column_count_full?: number | null
  column_count_linked?: number | null
}

export type AuthorizationSnap = {
  actor_user_id?: string
  actor_role?: string
  dataset_id?: string
  authorized_tables?: string[]
  acl_mode?: string
}

export function nodeLabel(nodeName: string): string {
  return NODE_LABELS[nodeName] || nodeName
}

export function failureClassLabel(fc: string | null | undefined): string | null {
  if (!fc) return null
  return FAILURE_CLASS_LABELS[fc] || fc
}

export function asSqlQuality(v: unknown): SqlQuality | null {
  if (!v || typeof v !== 'object') return null
  return v as SqlQuality
}

export function asAuthorization(v: unknown): AuthorizationSnap | null {
  if (!v || typeof v !== 'object') return null
  return v as AuthorizationSnap
}

export function linkStatusTone(status: string | null | undefined): string {
  switch (status) {
    case 'ok':
      return '#276749'
    case 'partial':
      return '#744210'
    case 'fallback_full':
      return '#744210'
    case 'failed':
      return '#c53030'
    default:
      return '#4a5568'
  }
}

export function stepStatusTone(status: string): string {
  if (status === 'ok') return '#276749'
  if (status === 'error' || status === 'failed') return '#c53030'
  if (status === 'degraded') return '#744210'
  return '#4a5568'
}

/** First step with error/fail status — light N2 reuse on Analyze (not an Eval CLI). */
export function firstFailingStep(
  steps: Array<{ node_name: string; status: string; error_message?: string | null }>,
): { node_name: string; status: string; error_message?: string | null } | null {
  for (const s of steps) {
    if (s.status === 'error' || s.status === 'failed' || s.node_name === 'fail') {
      return s
    }
  }
  return null
}

export function sumStepLatencyMs(
  steps: Array<{ latency_ms?: number | null }>,
): number | null {
  let total = 0
  let any = false
  for (const s of steps) {
    if (s.latency_ms != null) {
      total += s.latency_ms
      any = true
    }
  }
  return any ? total : null
}

export function friendlySubmitError(err: { status?: number; message: string }): string {
  const msg = err.message || 'Submit failed'
  const lower = msg.toLowerCase()
  if (err.status === 429 || lower.includes('budget') || lower.includes('token budget')) {
    return `Budget / rate limit: ${msg}`
  }
  if (lower.includes('capacity') || lower.includes('in_flight') || lower.includes('queue')) {
    return `Capacity: ${msg}`
  }
  return msg
}

export function artifactPipelineHint(types: string[]): string {
  const order = ['sql', 'table', 'summary', 'chart', 'report']
  const present = order.filter((t) => types.includes(t))
  if (present.length === 0) return 'No artifacts recorded yet.'
  return `Produced along Skill path: ${present.join(' → ')} (after execute → summarize → charts → report as applicable).`
}
