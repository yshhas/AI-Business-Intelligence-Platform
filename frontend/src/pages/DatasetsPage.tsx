import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  bindPostgresRoDataset,
  listDatasets,
  previewDataset,
  uploadDataset,
} from '../api/datasets'
import { ApiError } from '../api/client'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Input,
  PageHeader,
  SpinnerBlock,
  StatusBadge,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '../components/ui'
import { getStoredWorkspace } from '../stores/authStore'
import type { Dataset, Preview } from '../types/dataset'

export function DatasetsPage() {
  const workspace = getStoredWorkspace()
  if (!workspace?.id) {
    return <Navigate to="/app" replace />
  }
  return (
    <DatasetsPageInner
      workspaceId={workspace.id}
      workspaceName={workspace.name}
      role={workspace.role || 'owner'}
    />
  )
}

function DatasetsPageInner({
  workspaceId,
  workspaceName,
  role,
}: {
  workspaceId: string
  workspaceName: string
  role: string
}) {
  const canMutate = role === 'owner' || role === 'analyst'
  const {
    data: listData,
    isLoading: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ['datasets', workspaceId],
    queryFn: () => listDatasets(workspaceId),
  })
  const items = listData?.items ?? []
  const [selected, setSelected] = useState<Dataset | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [roName, setRoName] = useState('Demo Postgres RO')
  const [roTables, setRoTables] = useState('public.demo_orders, public.demo_customers')
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [binding, setBinding] = useState(false)

  const loadError =
    queryError instanceof ApiError || queryError instanceof Error
      ? queryError.message
      : queryError
        ? 'Load failed'
        : null
  const displayError = error ?? loadError

  async function refresh() {
    setError(null)
    await refetch()
  }

  async function onUpload(e: FormEvent) {
    e.preventDefault()
    if (!file) {
      setError('Choose a .csv or .xlsx file')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const ds = await uploadDataset(workspaceId, file, name || undefined)
      setFile(null)
      setName('')
      await refresh()
      await openDataset(ds)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function onBindPostgresRo(e: FormEvent) {
    e.preventDefault()
    const tables = roTables
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    if (!roName.trim() || tables.length < 1 || tables.length > 2) {
      setError('Provide a name and 1–2 schema-qualified tables (public.table)')
      return
    }
    setBinding(true)
    setError(null)
    try {
      const ds = await bindPostgresRoDataset(workspaceId, {
        name: roName.trim(),
        tables,
      })
      await refresh()
      await openDataset(ds)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bind failed')
    } finally {
      setBinding(false)
    }
  }

  async function openDataset(ds: Dataset) {
    setSelected(ds)
    setPreview(null)
    setError(null)
    try {
      const p = await previewDataset(workspaceId, ds.id, 50)
      setPreview(p)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Preview failed')
    }
  }

  return (
    <section className="workspace-page">
      <PageHeader
        title="Datasets"
        description={
          <>
            Upload files to DuckDB or bind read-only Postgres. Workspace{' '}
            <strong>{workspaceName}</strong> · role <code className="mono">{role}</code>
            {!canMutate ? ' · viewer (upload/bind disabled)' : null}
          </>
        }
      />

      {!canMutate ? (
        <Alert variant="warning">
          Your role is view-only. Upload and Postgres bind are disabled.
        </Alert>
      ) : null}

      {canMutate ? (
        <div className="grid-2">
          <Card>
            <CardHeader title="Upload file" description="CSV or Excel → DuckDB table." />
            <CardBody>
              <form className="stack" onSubmit={onUpload}>
                <label className="field file-field">
                  <span className="field-label">File (.csv / .xlsx)</span>
                  <input
                    type="file"
                    accept=".csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Display name (optional)</span>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Sales Q1"
                  />
                </label>
                <Button type="submit" loading={uploading}>
                  {uploading ? 'Uploading…' : 'Upload'}
                </Button>
              </form>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Bind Postgres (read-only)"
              description={
                <>
                  DSN from server env <code>POSTGRES_RO_DSN</code>. Tables must be{' '}
                  <code>public.*</code> (max 2).
                </>
              }
            />
            <CardBody>
              <form className="stack" onSubmit={onBindPostgresRo}>
                <label className="field">
                  <span className="field-label">Display name</span>
                  <Input value={roName} onChange={(e) => setRoName(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field-label">Tables (comma-separated)</span>
                  <Input
                    value={roTables}
                    onChange={(e) => setRoTables(e.target.value)}
                    placeholder="public.demo_orders, public.demo_customers"
                  />
                </label>
                <Button type="submit" loading={binding}>
                  {binding ? 'Binding…' : 'Bind readonly source'}
                </Button>
              </form>
            </CardBody>
          </Card>
        </div>
      ) : null}

      {displayError ? <Alert variant="error">{displayError}</Alert> : null}

      {loading && items.length === 0 ? (
        <SpinnerBlock label="Loading datasets…" />
      ) : (
        <div className="split-pane split-pane--datasets">
          <Card>
            <CardHeader title="List" description={`${items.length} dataset(s)`} />
            <CardBody>
              {items.length === 0 ? (
                <EmptyState
                  title="No datasets yet"
                  description={
                    canMutate
                      ? 'Upload a file or bind a Postgres source to get started.'
                      : 'Ask an owner or analyst to add a dataset.'
                  }
                />
              ) : (
                <ul className="panel-list">
                  {items.map((ds) => (
                    <li key={ds.id}>
                      <button
                        type="button"
                        className={
                          selected?.id === ds.id
                            ? 'list-item-btn is-selected'
                            : 'list-item-btn'
                        }
                        onClick={() => void openDataset(ds)}
                      >
                        <span className="list-item-btn__title">
                          {ds.name}
                          <StatusBadge status={ds.status} />
                        </span>
                        <span className="list-item-btn__meta">
                          {ds.source_type} · {ds.row_count} rows ·{' '}
                          {ds.schema_json?.length ?? 0} cols
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Schema & preview" />
            <CardBody>
              {!selected ? (
                <EmptyState
                  title="Select a dataset"
                  description="Choose an item from the list to inspect schema and sample rows."
                />
              ) : (
                <div className="detail-stack">
                  <div className="meta-row">
                    <strong>{selected.name}</strong>
                    <StatusBadge status={selected.status} />
                    <span className="caption">
                      {selected.source_type} · {selected.duckdb_table}
                    </span>
                  </div>

                  <div className="section-block">
                    <h3 className="section-block__title">Schema</h3>
                    {(selected.schema_json ?? []).length === 0 ? (
                      <p className="caption">No schema columns.</p>
                    ) : (
                      <Table>
                        <THead>
                          <TR>
                            <TH>Column</TH>
                            <TH>Type</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {(selected.schema_json ?? []).map((c) => (
                            <TR key={c.name}>
                              <TD>{c.name}</TD>
                              <TD>
                                <code className="mono">{c.type}</code>
                              </TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    )}
                  </div>

                  <div className="section-block">
                    <h3 className="section-block__title">Preview</h3>
                    {!preview ? (
                      <p className="caption">No preview.</p>
                    ) : (
                      <Table>
                        <THead>
                          <TR>
                            {preview.columns.map((c) => (
                              <TH key={c}>{c}</TH>
                            ))}
                          </TR>
                        </THead>
                        <TBody>
                          {preview.rows.map((row, idx) => (
                            <TR key={idx}>
                              {preview.columns.map((c) => (
                                <TD key={c}>{String(row[c] ?? '')}</TD>
                              ))}
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    )}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      <p className="caption">
        <Link to="/app">← Dashboard</Link>
      </p>
    </section>
  )
}
