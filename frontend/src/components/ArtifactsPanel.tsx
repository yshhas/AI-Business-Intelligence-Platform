import { useState, type ReactNode } from 'react'
import type { RunArtifact } from '../types/task'
import { artifactPipelineHint } from '../lib/traceLabels'
import { Alert, Button, StatusBadge } from './ui'

export function ArtifactsPanel({
  artifacts,
  selectedId,
  onSelect,
  detail,
}: {
  artifacts: RunArtifact[]
  selectedId: string | null
  onSelect: (id: string) => void
  detail: RunArtifact | null
}): ReactNode {
  const [showRaw, setShowRaw] = useState(false)

  if (artifacts.length === 0) return null

  const types = artifacts.map((a) => a.type)

  return (
    <div className="panel-block">
      <h3 className="panel-block__title">Artifacts</h3>
      <p className="panel-block__desc">
        How outputs were produced for this Run (lineage from existing artifact
        records — not a Report Center).
      </p>
      <p className="caption">{artifactPipelineHint(types)}</p>

      <ul className="panel-list-plain panel-list-plain--tight">
        {artifacts.map((a) => (
          <li key={a.id}>
            <button
              type="button"
              className={
                selectedId === a.id
                  ? 'artifact-item__btn is-selected'
                  : 'artifact-item__btn'
              }
              onClick={() => onSelect(a.id)}
            >
              <code>{a.type}</code> · <StatusBadge status={a.status} />
              {a.title ? ` · ${a.title}` : ''}
            </button>
            <div className="caption mono">{a.id}</div>
          </li>
        ))}
      </ul>

      {detail ? (
        <div className="artifact-detail">
          <p className="caption">
            Lineage: skill{' '}
            <code>{String(detail.lineage?.skill_id || detail.skill_id || '—')}</code>
            {detail.lineage?.source_type ? (
              <>
                {' '}
                · plane <code>{String(detail.lineage.source_type)}</code>
              </>
            ) : null}
            {detail.lineage?.dataset_id ? (
              <>
                {' '}
                · dataset <code>{String(detail.lineage.dataset_id).slice(0, 8)}…</code>
              </>
            ) : null}
          </p>
          {detail.status === 'unavailable' ? (
            <Alert variant="warning">
              Unavailable — recorded for lineage; payload not resolvable.
            </Alert>
          ) : (
            <>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setShowRaw((v) => !v)}
              >
                {showRaw ? 'Hide raw payload' : 'Show raw payload'}
              </Button>
              {showRaw ? (
                <pre className="code-block code-block--scroll">
                  {JSON.stringify(
                    {
                      content_ref: detail.content_ref,
                      payload: detail.payload,
                    },
                    null,
                    2,
                  )}
                </pre>
              ) : (
                <p className="caption">
                  Payload collapsed — expand only when debugging.
                </p>
              )}
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}
