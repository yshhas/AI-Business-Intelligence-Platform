import type { HTMLAttributes } from 'react'
import { cx } from './cx'

export type StatusTone =
  | 'pending'
  | 'running'
  | 'ready'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'warning'
  | 'neutral'

const STATUS_TONE_MAP: Record<string, StatusTone> = {
  pending: 'pending',
  queued: 'pending',
  running: 'running',
  processing: 'running',
  ready: 'ready',
  succeeded: 'succeeded',
  completed: 'succeeded',
  success: 'succeeded',
  failed: 'failed',
  error: 'failed',
  cancelled: 'cancelled',
  canceled: 'cancelled',
  denied: 'failed',
  unavailable: 'warning',
  warning: 'warning',
}

function resolveTone(status: string, tone?: StatusTone): StatusTone {
  if (tone) return tone
  const key = status.trim().toLowerCase()
  return STATUS_TONE_MAP[key] ?? 'neutral'
}

export type StatusBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  /** Raw status string from API (e.g. pending, running, ready). */
  status: string
  /** Optional override of visual tone. */
  tone?: StatusTone
  /** Display label; defaults to `status`. */
  label?: string
  showDot?: boolean
}

export function StatusBadge({
  status,
  tone,
  label,
  showDot = true,
  className,
  ...rest
}: StatusBadgeProps) {
  const resolved = resolveTone(status, tone)
  return (
    <span
      className={cx('status-badge', `status-badge--${resolved}`, className)}
      {...rest}
    >
      {showDot ? <span className="status-badge__dot" aria-hidden /> : null}
      <span>{label ?? status}</span>
    </span>
  )
}
