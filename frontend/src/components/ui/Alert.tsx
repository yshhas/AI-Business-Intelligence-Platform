import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export type AlertVariant = 'error' | 'warning' | 'success' | 'info'

export type AlertProps = HTMLAttributes<HTMLDivElement> & {
  variant?: AlertVariant
  title?: ReactNode
  children?: ReactNode
}

export function Alert({
  variant = 'info',
  title,
  className,
  children,
  role,
  ...rest
}: AlertProps) {
  return (
    <div
      className={cx('alert', `alert--${variant}`, className)}
      role={role ?? (variant === 'error' ? 'alert' : 'status')}
      {...rest}
    >
      <div>
        {title != null ? <div className="alert__title">{title}</div> : null}
        {children}
      </div>
    </div>
  )
}
