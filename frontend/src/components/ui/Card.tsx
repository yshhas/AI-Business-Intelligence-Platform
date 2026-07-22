import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export type CardProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode
}

export function Card({ className, children, ...rest }: CardProps) {
  return (
    <div className={cx('card', className)} {...rest}>
      {children}
    </div>
  )
}

export type CardHeaderProps = HTMLAttributes<HTMLDivElement> & {
  title?: ReactNode
  description?: ReactNode
  children?: ReactNode
}

export function CardHeader({
  className,
  title,
  description,
  children,
  ...rest
}: CardHeaderProps) {
  return (
    <div className={cx('card__header', className)} {...rest}>
      {title != null ? <div className="card__title">{title}</div> : null}
      {description != null ? (
        <div className="card__description">{description}</div>
      ) : null}
      {children}
    </div>
  )
}

export type CardBodyProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode
}

export function CardBody({ className, children, ...rest }: CardBodyProps) {
  return (
    <div className={cx('card__body', className)} {...rest}>
      {children}
    </div>
  )
}

export type CardFooterProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode
}

export function CardFooter({ className, children, ...rest }: CardFooterProps) {
  return (
    <div className={cx('card__footer', className)} {...rest}>
      {children}
    </div>
  )
}
