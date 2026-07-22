import { forwardRef, type InputHTMLAttributes } from 'react'
import { cx } from './cx'

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input({ className, invalid, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cx('input', invalid && 'is-invalid', className)}
        aria-invalid={invalid || undefined}
        {...rest}
      />
    )
  },
)
