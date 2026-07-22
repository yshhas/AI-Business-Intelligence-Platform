// Shared helpers to render task result: summary, SQL, preview, charts, report.

import type { ReactNode } from 'react'
import { parseCharts, parseReport } from '../types/result'
import { asSqlQuality } from '../lib/traceLabels'
import {
  Alert,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from './ui'
import { ChartView } from './ChartView'
import { linkToneClass } from './linkTone'
import { ReportView } from './ReportView'

type Preview = {
  columns?: unknown
  rows?: unknown
}

function asString(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null
}

function asPreview(v: unknown): Preview | null {
  if (!v || typeof v !== 'object') return null
  return v as Preview
}

export function TaskResultPanel({
  resultJson,
  llmTotalTokens,
}: {
  resultJson: Record<string, unknown> | null | undefined
  llmTotalTokens?: number | null
}): ReactNode {
  if (!resultJson) return null

  const summary = asString(resultJson.summary)
  const sql = asString(resultJson.sql)
  const preview = asPreview(resultJson.table_preview)
  const columns = Array.isArray(preview?.columns)
    ? preview.columns.map(String)
    : []
  const rows = Array.isArray(preview?.rows)
    ? (preview.rows as Record<string, unknown>[])
    : []
  const mock = resultJson.mock === true
  const charts = parseCharts(resultJson.charts)
  const report = parseReport(resultJson.report)
  const limitations = Array.isArray(resultJson.limitations)
    ? resultJson.limitations.map(String)
    : []
  const platform =
    resultJson.platform && typeof resultJson.platform === 'object'
      ? (resultJson.platform as Record<string, unknown>)
      : null
  const skillId =
    platform && typeof platform.skill_id === 'string' ? platform.skill_id : null
  const skillVersion =
    platform && typeof platform.skill_version === 'string' ? platform.skill_version : null
  const toolIds = Array.isArray(platform?.tool_ids)
    ? platform.tool_ids.map(String)
    : []
  const policyIds = Array.isArray(platform?.policy_ids)
    ? platform.policy_ids.map(String)
    : []
  const dataPlane =
    platform?.data_plane && typeof platform.data_plane === 'object'
      ? (platform.data_plane as Record<string, unknown>)
      : null
  const dataPlaneType =
    dataPlane && typeof dataPlane.source_type === 'string' ? dataPlane.source_type : null
  const sqlQuality = asSqlQuality(platform?.sql_quality)

  return (
    <div className="panel-block">
      <h3 className="panel-block__title">Result</h3>

      {skillId ? (
        <p className="panel-meta">
          Skill: <code>{skillId}</code>
          {skillVersion ? (
            <>
              @<code>{skillVersion}</code>
            </>
          ) : null}
          {dataPlaneType ? (
            <>
              {' '}
              · data plane: <code>{dataPlaneType}</code>
            </>
          ) : null}
          {llmTotalTokens != null ? (
            <>
              {' '}
              · tokens: <code>{llmTotalTokens}</code>
            </>
          ) : null}
          {toolIds.length > 0 ? (
            <>
              {' '}
              · tools: <code>{toolIds.slice(0, 6).join(', ')}</code>
            </>
          ) : null}
          {policyIds.length > 0 ? (
            <>
              {' '}
              · policies: <code>{policyIds.join(', ')}</code>
            </>
          ) : null}
        </p>
      ) : null}

      {mock ? (
        <Alert variant="warning">Mock runtime result (ANALYSIS_RUNTIME=mock)</Alert>
      ) : null}

      {summary ? (
        <p className="result-summary">
          <strong>Summary:</strong> {summary}
        </p>
      ) : null}

      {sql ? (
        <div className="section-block">
          <h4 className="section-block__title">SQL</h4>
          {sqlQuality ? (
            <p className="caption">
              Linked{' '}
              <strong className={linkToneClass(sqlQuality.link_status)}>
                {sqlQuality.link_status}
              </strong>
              {sqlQuality.column_count_linked != null &&
              sqlQuality.column_count_full != null
                ? ` · ${sqlQuality.column_count_linked}/${sqlQuality.column_count_full} columns`
                : null}
              {sqlQuality.link_status === 'fallback_full' ? (
                <span className="tone-warning"> · explicit fallback (not silent)</span>
              ) : null}
            </p>
          ) : null}
          <pre className="code-block">{sql}</pre>
        </div>
      ) : null}

      {columns.length > 0 ? (
        <div className="section-block">
          <h4 className="section-block__title">Preview</h4>
          <Table>
            <THead>
              <TR>
                {columns.map((c) => (
                  <TH key={c}>{c}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {rows.length === 0 ? (
                <TR>
                  <TD colSpan={columns.length}>No rows</TD>
                </TR>
              ) : (
                rows.slice(0, 50).map((row, i) => (
                  <TR key={i}>
                    {columns.map((c) => (
                      <TD key={c}>{row[c] == null ? '' : String(row[c])}</TD>
                    ))}
                  </TR>
                ))
              )}
            </TBody>
          </Table>
        </div>
      ) : null}

      {charts.length > 0 ? (
        <div className="section-block">
          <h4 className="section-block__title">Charts</h4>
          {charts.map((c, i) => (
            <ChartView key={c.id || i} chart={c} />
          ))}
        </div>
      ) : null}

      {report && (report.markdown || (report.sections && report.sections.length > 0)) ? (
        <ReportView report={report} />
      ) : null}

      {limitations.length > 0 ? (
        <div className="section-block">
          <h4 className="section-block__title">Limitations</h4>
          <ul className="panel-list-plain">
            {limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
