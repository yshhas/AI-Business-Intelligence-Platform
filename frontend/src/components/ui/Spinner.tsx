import type { HTMLAttributes } from 'react'
import { cx } from './cx'

export type SpinnerSize = 'sm' | 'md' | 'lg'

export type SpinnerProps = HTMLAttributes<HTMLDivElement> & {
  size?: SpinnerSize
  label?: string
}

export function Spinner({
  size = 'md',
  label = 'Loading',
  className,
  ...rest
}: SpinnerProps) {
  return (
    <div
      className={cx('spinner', size !== 'md' && `spinner--${size}`, className)}
      role="status"
      aria-label={label}
      {...rest}
    >
      <span className="sr-only">{label}</span>
    </div>
  )
}

export type SpinnerBlockProps = HTMLAttributes<HTMLDivElement> & {
  label?: string
  size?: SpinnerSize
}

export function SpinnerBlock({
  label = 'Loading…',
  size = 'md',
  className,
  ...rest
}: SpinnerBlockProps) {
  return (
    <div className={cx('spinner-block', className)} {...rest}>
      <Spinner size={size} label={label} />
      <span>{label}</span>
    </div>
  )
}
