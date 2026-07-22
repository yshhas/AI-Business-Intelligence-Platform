/** Render report.markdown with minimal markdown (headings + paragraphs). */

import type { ReactNode } from 'react'
import type { ReportDoc } from '../types/result'

export function ReportView({ report }: { report: ReportDoc }): ReactNode {
  const title = report.title || '分析简报'
  const md = report.markdown?.trim()

  return (
    <div className="report-view">
      <h3 className="panel-block__title">{title}</h3>
      {md ? (
        <div className="report-box">{renderSimpleMarkdown(md)}</div>
      ) : report.sections && report.sections.length > 0 ? (
        <div className="report-box">
          {report.sections.map((s, i) => (
            <div key={i} className="report-box__section">
              <h4 className="section-block__title">{s.heading}</h4>
              <pre className="report-body-pre">{s.body}</pre>
            </div>
          ))}
        </div>
      ) : (
        <p className="caption">No report</p>
      )}
    </div>
  )
}

function renderSimpleMarkdown(md: string): ReactNode {
  const blocks = md.split(/\n{2,}/)
  return blocks.map((block, i) => {
    const line = block.trim()
    if (line.startsWith('### ')) {
      return (
        <h5 key={i} className="report-md-h">
          {line.slice(4)}
        </h5>
      )
    }
    if (line.startsWith('## ')) {
      return (
        <h4 key={i} className="report-md-h">
          {line.slice(3)}
        </h4>
      )
    }
    if (line.startsWith('# ')) {
      return (
        <h4 key={i} className="report-md-h">
          {line.slice(2)}
        </h4>
      )
    }
    if (line.startsWith('```')) {
      const body = line.replace(/^```\w*\n?/, '').replace(/\n?```$/, '')
      return (
        <pre key={i} className="code-block">
          {body}
        </pre>
      )
    }
    return (
      <p key={i} className="report-md-p">
        {line}
      </p>
    )
  })
}
