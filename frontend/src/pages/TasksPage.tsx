import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  cancelTask,
  getTask,
  getTaskArtifact,
  getTaskExecution,
  getTaskSteps,
  listTaskArtifacts,
  listTasks,
} from '../api/tasks'
import { ApiError } from '../api/client'
import { TaskResultPanel } from '../components/TaskResultPanel'
import { ExecutionTracePanel } from '../components/ExecutionTracePanel'
import { ArtifactsPanel } from '../components/ArtifactsPanel'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  PageHeader,
  SpinnerBlock,
  StatusBadge,
} from '../components/ui'
import { getStoredWorkspace } from '../stores/authStore'
import type { ExecutionTrace, RunArtifact, Task, TaskStep } from '../types/task'

export function TasksPage() {
  const workspace = getStoredWorkspace()
  if (!workspace?.id) return <Navigate to="/app" replace />
  return <TasksPageInner workspaceId={workspace.id} />
}

function TasksPageInner({ workspaceId }: { workspaceId: string }) {
  const [policyDeniedOnly, setPolicyDeniedOnly] = useState(false)
  const {
    data: listData,
    isLoading: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ['tasks', workspaceId, policyDeniedOnly],
    queryFn: () =>
      listTasks(workspaceId, {
        policy_denied: policyDeniedOnly ? true : undefined,
      }),
  })
  const items = listData?.items ?? []
  const [selected, setSelected] = useState<Task | null>(null)
  const [steps, setSteps] = useState<TaskStep[]>([])
  const [trace, setTrace] = useState<ExecutionTrace | null>(null)
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([])
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [artifactDetail, setArtifactDetail] = useState<RunArtifact | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)

  const loadError = queryError instanceof Error ? queryError.message : null
  const displayError = error ?? loadError

  async function refreshList() {
    await refetch()
  }

  async function openTask(task: Task) {
    setError(null)
    setTrace(null)
    setArtifacts([])
    setSelectedArtifactId(null)
    setArtifactDetail(null)
    try {
      const t = await getTask(workspaceId, task.id)
      const s = await getTaskSteps(workspaceId, task.id)
      setSelected(t)
      setSteps(s.items)
      try {
        const ex = await getTaskExecution(workspaceId, task.id)
        setTrace(ex)
      } catch {
        setTrace(null)
      }
      try {
        const arts = await listTaskArtifacts(workspaceId, task.id)
        setArtifacts(arts.items)
      } catch {
        setArtifacts([])
      }
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Load failed')
    }
  }

  async function onSelectArtifact(id: string) {
    if (!selected) return
    setSelectedArtifactId(id)
    try {
      const d = await getTaskArtifact(workspaceId, selected.id, id)
      setArtifactDetail(d)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Artifact load failed')
    }
  }

  async function onCancel() {
    if (!selected) return
    setCancelling(true)
    setError(null)
    try {
      const t = await cancelTask(workspaceId, selected.id)
      setSelected(t)
      await refreshList()
      try {
        setTrace(await getTaskExecution(workspaceId, t.id))
      } catch {
        // ignore
      }
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Cancel failed')
    } finally {
      setCancelling(false)
    }
  }

  async function onTogglePolicyDenied() {
    setPolicyDeniedOnly((prev) => !prev)
    setError(null)
  }

  return (
    <section className="workspace-page">
      <PageHeader
        title="Tasks"
        description="Analysis run history — inspect status, steps, traces, and artifacts."
        actions={
          <Link to="/app/analyze" className="btn btn--primary btn--sm">
            New analysis
          </Link>
        }
      />

      <div className="filter-bar">
        <label className="filter-check">
          <input
            type="checkbox"
            checked={policyDeniedOnly}
            onChange={() => void onTogglePolicyDenied()}
          />
          Show policy_denied only
        </label>
      </div>

      {displayError ? <Alert variant="error">{displayError}</Alert> : null}

      {loading && items.length === 0 ? (
        <SpinnerBlock label="Loading tasks…" />
      ) : (
        <div className="split-pane">
          <Card>
            <CardHeader title="List" description={`${items.length} task(s)`} />
            <CardBody>
              {items.length === 0 ? (
                <EmptyState
                  title="No tasks yet"
                  description="Start an analysis run to populate history."
                  action={
                    <Link to="/app/analyze" className="btn btn--secondary btn--sm">
                      Go to Analyze
                    </Link>
                  }
                />
              ) : (
                <ul className="panel-list">
                  {items.map((t) => (
                    <li key={t.id}>
                      <button
                        type="button"
                        className={
                          selected?.id === t.id
                            ? 'list-item-btn is-selected'
                            : 'list-item-btn'
                        }
                        onClick={() => void openTask(t)}
                      >
                        <span className="list-item-btn__title">
                          <StatusBadge status={t.status} />
                          {t.policy_denied ? (
                            <StatusBadge status="denied" label="denied" />
                          ) : null}
                        </span>
                        <span className="list-item-btn__meta">
                          {t.source_type ? `${t.source_type} · ` : null}
                          {t.question.slice(0, 80)}
                          {t.question.length > 80 ? '…' : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Detail" />
            <CardBody>
              {!selected ? (
                <EmptyState
                  title="Select a task"
                  description="Choose a run from the list to inspect detail."
                />
              ) : (
                <div className="detail-stack">
                  <div className="meta-row">
                    <StatusBadge status={selected.status} />
                    {selected.failure_class ? (
                      <span className="caption">{selected.failure_class}</span>
                    ) : null}
                    {selected.policy_denied ? (
                      <StatusBadge status="denied" label="policy denied" />
                    ) : null}
                  </div>
                  <p className="caption mono">{selected.id}</p>
                  <p className="run-panel__question">{selected.question}</p>

                  {(selected.status === 'pending' || selected.status === 'running') && (
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      loading={cancelling}
                      onClick={() => void onCancel()}
                    >
                      {cancelling ? 'Cancelling…' : 'Cancel run'}
                    </Button>
                  )}

                  {selected.error_message ? (
                    <Alert variant="error">{selected.error_message}</Alert>
                  ) : null}

                  <div className="section-block">
                    <h3 className="section-block__title">Trace</h3>
                    <ExecutionTracePanel
                      trace={trace}
                      steps={steps}
                      llmTotalTokens={selected.llm_total_tokens}
                    />
                  </div>

                  <div className="section-block">
                    <h3 className="section-block__title">Artifacts & result</h3>
                    <ArtifactsPanel
                      artifacts={artifacts}
                      selectedId={selectedArtifactId}
                      onSelect={(id) => void onSelectArtifact(id)}
                      detail={artifactDetail}
                    />
                    <TaskResultPanel
                      resultJson={selected.result_json}
                      llmTotalTokens={selected.llm_total_tokens}
                    />
                  </div>

                  <div className="section-block">
                    <h3 className="section-block__title">Steps</h3>
                    {steps.length === 0 ? (
                      <p className="caption">No steps.</p>
                    ) : (
                      <ol className="step-list">
                        {steps.map((s) => (
                          <li key={s.id} className="step-item">
                            <div className="step-item__row">
                              <span className="step-item__name">{s.node_name}</span>
                              <StatusBadge status={s.status} />
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}
    </section>
  )
}
