import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export type BadgeVariant =
  | 'neutral'
  | 'accent'
  | 'success'
  | 'danger'
  | 'warning'
  | 'info'

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant
  children?: ReactNode
}

export function Badge({
  variant = 'neutral',
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span className={cx('badge', `badge--${variant}`, className)} {...rest}>
      {children}
    </span>
  )
}
