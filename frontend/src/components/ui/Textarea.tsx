import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cx } from './cx'

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ className, invalid, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        className={cx('textarea', invalid && 'is-invalid', className)}
        aria-invalid={invalid || undefined}
        {...rest}
      />
    )
  },
)
