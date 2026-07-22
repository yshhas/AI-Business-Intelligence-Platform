/** Lightweight SVG renderer for ChartSpec (bar | line). No chart library. */

import type { ChartSpec } from '../types/result'

const W = 420
const H = 220
const PAD = { t: 24, r: 16, b: 40, l: 48 }

const AXIS = '#a1a1aa'
const LABEL = '#71717a'
const SERIES = '#18181b'

export function ChartView({ chart }: { chart: ChartSpec }) {
  const xField = chart.spec.x.field
  const yField = chart.spec.y.field
  const rows = chart.spec.data.rows
    .map((r) => {
      const yRaw = r[yField]
      const y =
        typeof yRaw === 'number'
          ? yRaw
          : typeof yRaw === 'string'
            ? Number(yRaw)
            : NaN
      return { x: String(r[xField] ?? ''), y }
    })
    .filter((p) => p.x && Number.isFinite(p.y))

  if (rows.length === 0) {
    return <p className="caption">No plottable rows</p>
  }

  const ys = rows.map((p) => p.y)
  const yMin = Math.min(0, ...ys)
  const yMax = Math.max(...ys, 1)
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b

  const yScale = (v: number) =>
    PAD.t + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH

  return (
    <div className="chart-view">
      <h4 className="chart-view__title">
        {chart.title || chart.id || chart.type}
      </h4>
      {chart.rationale ? (
        <p className="caption">{chart.rationale}</p>
      ) : null}
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={chart.title || chart.type}
        className="chart-view__svg"
      >
        <line
          x1={PAD.l}
          y1={PAD.t}
          x2={PAD.l}
          y2={H - PAD.b}
          stroke={AXIS}
        />
        <line
          x1={PAD.l}
          y1={H - PAD.b}
          x2={W - PAD.r}
          y2={H - PAD.b}
          stroke={AXIS}
        />
        <text x={8} y={PAD.t + 8} fontSize={10} fill={LABEL}>
          {yMax.toFixed(0)}
        </text>
        <text x={8} y={H - PAD.b} fontSize={10} fill={LABEL}>
          {yMin.toFixed(0)}
        </text>

        {chart.type === 'bar' ? (
          rows.map((p, i) => {
            const bw = (innerW / rows.length) * 0.7
            const gap = innerW / rows.length
            const x = PAD.l + i * gap + (gap - bw) / 2
            const y = yScale(p.y)
            const h = H - PAD.b - y
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={y}
                  width={bw}
                  height={Math.max(h, 0)}
                  fill={SERIES}
                />
                <text
                  x={x + bw / 2}
                  y={H - PAD.b + 14}
                  textAnchor="middle"
                  fontSize={10}
                  fill={LABEL}
                >
                  {p.x.length > 8 ? `${p.x.slice(0, 7)}…` : p.x}
                </text>
              </g>
            )
          })
        ) : (
          <>
            <polyline
              fill="none"
              stroke={SERIES}
              strokeWidth={2}
              points={rows
                .map((p, i) => {
                  const x = PAD.l + (i / Math.max(rows.length - 1, 1)) * innerW
                  return `${x},${yScale(p.y)}`
                })
                .join(' ')}
            />
            {rows.map((p, i) => {
              const x = PAD.l + (i / Math.max(rows.length - 1, 1)) * innerW
              return (
                <g key={i}>
                  <circle cx={x} cy={yScale(p.y)} r={3.5} fill={SERIES} />
                  <text
                    x={x}
                    y={H - PAD.b + 14}
                    textAnchor="middle"
                    fontSize={10}
                    fill={LABEL}
                  >
                    {p.x.length > 8 ? `${p.x.slice(0, 7)}…` : p.x}
                  </text>
                </g>
              )
            })}
          </>
        )}
      </svg>
    </div>
  )
}
