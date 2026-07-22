/** Phase 5 result_json chart + report contracts (bar | line only). */

export type ChartType = 'bar' | 'line'

export type FieldRef = {
  field: string
  type: string
}

export type ChartSpec = {
  id?: string
  title?: string
  type: ChartType
  rationale?: string
  spec: {
    x: FieldRef
    y: FieldRef
    data: {
      columns: string[]
      rows: Record<string, unknown>[]
    }
  }
}

export type ReportDoc = {
  title?: string
  markdown?: string
  sections?: { heading: string; body: string }[]
}

export type AnalysisResult = {
  summary?: string
  sql?: string | null
  table_preview?: {
    columns?: string[]
    rows?: Record<string, unknown>[]
  }
  charts?: ChartSpec[]
  report?: ReportDoc | null
  limitations?: string[]
  mock?: boolean
}

export function parseCharts(raw: unknown): ChartSpec[] {
  if (!Array.isArray(raw)) return []
  const out: ChartSpec[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const c = item as Record<string, unknown>
    if (c.type !== 'bar' && c.type !== 'line') continue
    const spec = c.spec
    if (!spec || typeof spec !== 'object') continue
    const s = spec as Record<string, unknown>
    const data = s.data
    if (!data || typeof data !== 'object') continue
    const d = data as Record<string, unknown>
    if (!Array.isArray(d.columns) || !Array.isArray(d.rows)) continue
    const x = s.x as FieldRef | undefined
    const y = s.y as FieldRef | undefined
    if (!x?.field || !y?.field) continue
    out.push({
      id: typeof c.id === 'string' ? c.id : undefined,
      title: typeof c.title === 'string' ? c.title : undefined,
      type: c.type,
      rationale: typeof c.rationale === 'string' ? c.rationale : undefined,
      spec: {
        x,
        y,
        data: {
          columns: d.columns.map(String),
          rows: d.rows as Record<string, unknown>[],
        },
      },
    })
  }
  return out.slice(0, 2)
}

export function parseReport(raw: unknown): ReportDoc | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  return {
    title: typeof r.title === 'string' ? r.title : undefined,
    markdown: typeof r.markdown === 'string' ? r.markdown : undefined,
    sections: Array.isArray(r.sections)
      ? (r.sections as { heading: string; body: string }[])
      : undefined,
  }
}
