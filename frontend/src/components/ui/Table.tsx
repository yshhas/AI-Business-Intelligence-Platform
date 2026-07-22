import type { HTMLAttributes, ReactNode, TableHTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cx } from './cx'

export type TableProps = TableHTMLAttributes<HTMLTableElement> & {
  children?: ReactNode
  /** Wrap table in scrollable bordered container (default true). */
  wrap?: boolean
  wrapClassName?: string
}

export function Table({
  className,
  children,
  wrap = true,
  wrapClassName,
  ...rest
}: TableProps) {
  const table = (
    <table className={cx('table', className)} {...rest}>
      {children}
    </table>
  )
  if (!wrap) return table
  return <div className={cx('table-wrap', wrapClassName)}>{table}</div>
}

export function THead({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={className} {...rest}>
      {children}
    </thead>
  )
}

export function TBody({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={className} {...rest}>
      {children}
    </tbody>
  )
}

export function TR({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={className} {...rest}>
      {children}
    </tr>
  )
}

export function TH({
  className,
  children,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={className} {...rest}>
      {children}
    </th>
  )
}

export function TD({
  className,
  children,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={className} {...rest}>
      {children}
    </td>
  )
}
