import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cx } from './cx'

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  function Select({ className, invalid, children, ...rest }, ref) {
    return (
      <select
        ref={ref}
        className={cx('select', invalid && 'is-invalid', className)}
        aria-invalid={invalid || undefined}
        {...rest}
      >
        {children}
      </select>
    )
  },
)
