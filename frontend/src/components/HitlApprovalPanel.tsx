import { useState } from 'react'
import { Alert, Button, Textarea } from './ui'
import { extractHitlContext } from '../lib/hitl'
import type { Task } from '../types/task'

export type HitlApprovalPanelProps = {
  task: Task
  canAct: boolean
  busy?: boolean
  actionError?: string | null
  onApprove: () => void | Promise<void>
  onReject: (reason?: string) => void | Promise<void>
  onCancel: () => void | Promise<void>
}

/**
 * HITL H3: awaiting_approval banner + SQL snapshot + approve/reject/cancel.
 * Buttons are gated by `canAct` (creator/owner); backend still enforces auth.
 */
export function HitlApprovalPanel({
  task,
  canAct,
  busy = false,
  actionError = null,
  onApprove,
  onReject,
  onCancel,
}: HitlApprovalPanelProps) {
  const [reason, setReason] = useState('')
  const [showRejectReason, setShowRejectReason] = useState(false)
  const ctx = extractHitlContext(task.result_json)
  const resumePending = Boolean(task.hitl_resume_requested)

  return (
    <div className="hitl-panel" role="region" aria-label="SQL approval">
      <Alert variant="warning">
        {resumePending
          ? 'Approval submitted — waiting for the worker to resume execute.'
          : 'SQL approval required before execute. Review the SQL snapshot, then approve or reject.'}
      </Alert>

      {!canAct && !resumePending ? (
        <p className="caption">
          View only — approve/reject is limited to the run creator or workspace owner.
        </p>
      ) : null}

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

      <div className="hitl-panel__meta">
        {ctx.phase ? (
          <span>
            phase <code>{ctx.phase}</code>
          </span>
        ) : null}
        {ctx.sqlSha256 ? (
          <span>
            sql_sha256 <code className="hitl-panel__hash">{ctx.sqlSha256}</code>
          </span>
        ) : null}
        {task.approval_requested_at ? (
          <span>
            requested <code>{task.approval_requested_at}</code>
          </span>
        ) : null}
      </div>

      <div className="section-block">
        <h4 className="section-block__title">SQL snapshot</h4>
        {ctx.sql ? (
          <pre className="code-block hitl-panel__sql">{ctx.sql}</pre>
        ) : (
          <p className="caption">No SQL snapshot available on this run yet.</p>
        )}
        {ctx.note ? <p className="caption">{ctx.note}</p> : null}
      </div>

      {canAct && !resumePending ? (
        <div className="hitl-panel__actions">
          <Button
            type="button"
            size="sm"
            disabled={busy}
            loading={busy}
            onClick={() => void onApprove()}
          >
            Approve
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => setShowRejectReason((v) => !v)}
          >
            Reject
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            disabled={busy}
            onClick={() => void onCancel()}
          >
            Cancel run
          </Button>
        </div>
      ) : null}

      {canAct && !resumePending && showRejectReason ? (
        <div className="hitl-panel__reject">
          <label className="field">
            <span className="field-label">Reject reason (optional)</span>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="Why this SQL should not run"
              disabled={busy}
            />
          </label>
          <Button
            type="button"
            variant="danger"
            size="sm"
            disabled={busy}
            loading={busy}
            onClick={() => void onReject(reason.trim() || undefined)}
          >
            Confirm reject
          </Button>
        </div>
      ) : null}
    </div>
  )
}
