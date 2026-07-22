import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export type PageHeaderProps = HTMLAttributes<HTMLElement> & {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({
  title,
  description,
  actions,
  className,
  ...rest
}: PageHeaderProps) {
  return (
    <header className={cx('page-header', className)} {...rest}>
      <div className="page-header__text">
        <h1 className="page-title">{title}</h1>
        {description != null ? <p className="page-desc">{description}</p> : null}
      </div>
      {actions != null ? (
        <div className="page-header__actions">{actions}</div>
      ) : null}
    </header>
  )
}
