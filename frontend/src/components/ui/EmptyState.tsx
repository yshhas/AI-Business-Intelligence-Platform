import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export type EmptyStateProps = HTMLAttributes<HTMLDivElement> & {
  title: ReactNode
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
  ...rest
}: EmptyStateProps) {
  return (
    <div className={cx('empty-state', className)} {...rest}>
      {icon != null ? <div className="empty-state__icon">{icon}</div> : null}
      <div className="empty-state__title">{title}</div>
      {description != null ? (
        <div className="empty-state__description">{description}</div>
      ) : null}
      {action != null ? <div className="empty-state__action">{action}</div> : null}
    </div>
  )
}
