import type { ReactNode } from 'react'
import type { ExecutionTrace, TaskStep } from '../types/task'
import {
  asAuthorization,
  asSqlQuality,
  failureClassLabel,
  firstFailingStep,
  nodeLabel,
  sumStepLatencyMs,
} from '../lib/traceLabels'
import { Alert, StatusBadge } from './ui'
import { linkToneClass } from './linkTone'

export function ExecutionTracePanel({
  trace,
  steps,
  llmTotalTokens,
}: {
  trace: ExecutionTrace | null | undefined
  steps?: TaskStep[]
  llmTotalTokens?: number | null
}): ReactNode {
  if (!trace) return null

  const execution = trace.execution || {}
  const toolCalls = Array.isArray(execution.tool_calls) ? execution.tool_calls : []
  const decisions = Array.isArray(execution.policy_decisions)
    ? execution.policy_decisions
    : []
  const artifacts = Array.isArray(execution.artifacts) ? execution.artifacts : []
  const summary = (execution.summary || {}) as Record<string, unknown>
  const incomplete = summary.incomplete === true
  const sqlQuality = asSqlQuality(trace.sql_quality)
  const authz = asAuthorization(trace.authorization)
  const deny = decisions.find((pd) => pd.ok === false)
  const allowAll =
    decisions.length > 0 && decisions.every((pd) => pd.ok === true)
  const stepList = steps || []
  const firstFail = firstFailingStep(stepList)
  const latencySum = sumStepLatencyMs(stepList)
  const fcLabel = failureClassLabel(trace.failure_class)

  return (
    <div className="panel-block">
      <h3 className="panel-block__title">Run explainability</h3>
      <p className="panel-block__desc">
        Analyze view of this Run — not a Trace Explorer. Facts from Trace / steps /
        artifacts only.
      </p>

      <div className="panel-meta">
        <code>{trace.skill_id || '—'}</code>
        {trace.skill_version ? (
          <>
            @<code>{trace.skill_version}</code>
          </>
        ) : null}
        {trace.source_type ? (
          <>
            {' '}
            · plane <code>{trace.source_type}</code>
          </>
        ) : null}
        <StatusBadge status={trace.status} />
        {fcLabel ? <span className="tone-warning">{fcLabel}</span> : null}
        {trace.policy_denied ? (
          <StatusBadge status="denied" label="policy denied" />
        ) : null}
        {incomplete ? <BadgeWarn text="incomplete" /> : null}
      </div>

      <div className="strip-grid">
        <StripCard title="Schema used">
          {sqlQuality ? (
            <>
              <div>
                Link:{' '}
                <strong className={linkToneClass(sqlQuality.link_status)}>
                  {sqlQuality.link_status || '—'}
                </strong>
                {sqlQuality.link_method ? (
                  <>
                    {' '}
                    · <code>{sqlQuality.link_method}</code>
                  </>
                ) : null}
              </div>
              {sqlQuality.link_reason ? (
                <div className="tone-warning caption">
                  reason: {sqlQuality.link_reason}
                </div>
              ) : null}
              <div>
                Tables:{' '}
                <code>{(sqlQuality.selected_tables || []).join(', ') || '—'}</code>
              </div>
              <div>
                Columns (
                {sqlQuality.column_count_linked ??
                  (sqlQuality.selected_columns || []).length}
                {sqlQuality.column_count_full != null
                  ? ` / ${sqlQuality.column_count_full}`
                  : ''}
                ): <ColumnList columns={sqlQuality.selected_columns || []} />
              </div>
              {sqlQuality.link_status === 'fallback_full' ? (
                <div className="tone-warning caption">
                  Explicit fallback — full/capped schema used; not a silent success.
                </div>
              ) : null}
              {sqlQuality.link_status === 'failed' ? (
                <div className="tone-danger caption">
                  Schema linking failed — unusable schema view.
                </div>
              ) : null}
            </>
          ) : (
            <span className="tone-muted">No sql_quality on this Trace yet.</span>
          )}
          {authz?.authorized_tables && authz.authorized_tables.length > 0 ? (
            <div className="caption">
              Authorized tables: <code>{authz.authorized_tables.join(', ')}</code>
              {authz.acl_mode ? (
                <>
                  {' '}
                  · ACL <code>{authz.acl_mode}</code>
                </>
              ) : null}
            </div>
          ) : null}
        </StripCard>

        <StripCard title="Why this SQL">
          {sqlQuality ? (
            <>
              <div>
                Prompt used the{' '}
                <strong>
                  {sqlQuality.link_status === 'fallback_full'
                    ? 'recovered (fallback) schema view'
                    : 'linked schema view'}
                </strong>
                .
              </div>
              <div>
                status <code>{sqlQuality.link_status}</code>
                {sqlQuality.link_method ? (
                  <>
                    {' '}
                    · method <code>{sqlQuality.link_method}</code>
                  </>
                ) : null}
              </div>
            </>
          ) : (
            <span className="tone-muted">Linking metadata unavailable.</span>
          )}
          {deny ? (
            <div className="tone-danger caption">
              Gate may have rejected drafts — see Policy below.
            </div>
          ) : null}
        </StripCard>

        <StripCard title="Policy">
          {decisions.length === 0 ? (
            <span className="tone-muted">No policy decisions recorded.</span>
          ) : allowAll ? (
            <span className="tone-success">
              Allow — <code>{String(decisions[0]?.policy_id || 'sql.select_gate')}</code>
            </span>
          ) : deny ? (
            <>
              <span className="tone-danger">
                Deny — <code>{String(deny.policy_id)}</code>
              </span>
              {deny.reason ? (
                <div className="tone-danger caption">{String(deny.reason)}</div>
              ) : null}
            </>
          ) : (
            <span className="tone-muted">{decisions.length} decision(s)</span>
          )}
          {trace.policy_denied ? (
            <div className="tone-danger caption">Run flagged policy_denied.</div>
          ) : null}
        </StripCard>

        <StripCard title="Resources">
          <div>
            Tokens:{' '}
            {llmTotalTokens != null ? (
              <code>{llmTotalTokens}</code>
            ) : (
              <span className="tone-muted">—</span>
            )}
          </div>
          <div>
            Step latency sum:{' '}
            {latencySum != null ? (
              <code>{latencySum}ms</code>
            ) : (
              <span className="tone-muted">—</span>
            )}
          </div>
        </StripCard>
      </div>

      {firstFail ? (
        <Alert variant="error">
          First failure: <strong>{nodeLabel(firstFail.node_name)}</strong> (
          <code>{firstFail.node_name}</code>) — {firstFail.status}
          {firstFail.error_message ? `: ${firstFail.error_message}` : ''}
        </Alert>
      ) : null}

      {authz ? (
        <div className="section-block">
          <h4 className="section-block__title">Authorization</h4>
          <p className="caption">
            Role <code>{authz.actor_role || '—'}</code>
            {authz.dataset_id ? (
              <>
                {' '}
                · dataset <code>{authz.dataset_id.slice(0, 8)}…</code>
              </>
            ) : null}
            {authz.acl_mode ? (
              <>
                {' '}
                · mode <code>{authz.acl_mode}</code>
              </>
            ) : null}
          </p>
          {authz.authorized_tables && authz.authorized_tables.length > 0 ? (
            <p className="caption">
              Tables: <code>{authz.authorized_tables.join(', ')}</code>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="section-block">
        <h4 className="section-block__title">
          Policy decisions ({decisions.length})
        </h4>
        {decisions.length === 0 ? (
          <p className="caption">None recorded yet.</p>
        ) : (
          <ul className="panel-list-plain">
            {decisions.map((pd) => (
              <li key={String(pd.decision_id ?? pd.seq)}>
                <code>{String(pd.policy_id)}</code> —{' '}
                {pd.ok ? (
                  <span className="tone-success">allow</span>
                ) : (
                  <span className="tone-danger">deny</span>
                )}
                {pd.tool_id ? (
                  <>
                    {' '}
                    · tool <code>{String(pd.tool_id)}</code>
                  </>
                ) : null}
                {!pd.ok && pd.reason ? (
                  <div className="tone-danger caption">{String(pd.reason)}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="section-block">
        <h4 className="section-block__title">Tool calls ({toolCalls.length})</h4>
        {toolCalls.length === 0 ? (
          <p className="caption">None recorded yet.</p>
        ) : (
          <ul className="panel-list-plain">
            {toolCalls.map((tc) => (
              <li key={String(tc.call_id ?? tc.seq)}>
                <code>{String(tc.tool_id)}</code> — {String(tc.status)}
                {tc.latency_ms != null ? ` (${String(tc.latency_ms)}ms)` : ''}
                {tc.error_message ? (
                  <span className="tone-danger"> · {String(tc.error_message)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="section-block">
        <h4 className="section-block__title">
          Artifact refs ({artifacts.length})
        </h4>
        {artifacts.length === 0 ? (
          <p className="caption">
            None recorded yet — see Artifacts panel when available.
          </p>
        ) : (
          <ul className="panel-list-plain">
            {artifacts.map((a) => (
              <li key={String(a.artifact_id)}>
                <code>{String(a.type)}</code>
                {a.status ? ` · ${String(a.status)}` : ''}
                {a.artifact_id ? (
                  <>
                    {' '}
                    · <code>{String(a.artifact_id)}</code>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function BadgeWarn({ text }: { text: string }): ReactNode {
  return <span className="tone-warning caption">{text}</span>
}

function StripCard({
  title,
  children,
}: {
  title: string
  children: ReactNode
}): ReactNode {
  return (
    <div className="strip-card">
      <div className="strip-card__title">{title}</div>
      <div className="strip-card__body">{children}</div>
    </div>
  )
}

function ColumnList({ columns }: { columns: string[] }): ReactNode {
  if (columns.length === 0) return <span className="tone-muted">—</span>
  const max = 8
  const shown = columns.slice(0, max)
  const rest = columns.length - shown.length
  return (
    <>
      <code>{shown.join(', ')}</code>
      {rest > 0 ? <span className="tone-muted"> (+{rest} more)</span> : null}
    </>
  )
}
