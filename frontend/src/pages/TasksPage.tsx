import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  approveTask,
  cancelTask,
  getTask,
  getTaskArtifact,
  getTaskExecution,
  getTaskSteps,
  listTaskArtifacts,
  listTasks,
  rejectTask,
} from '../api/tasks'
import { ApiError } from '../api/client'
import { HitlApprovalPanel } from '../components/HitlApprovalPanel'
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
import { getStoredUser, getStoredWorkspace } from '../stores/authStore'
import {
  canActOnHitl,
  isActiveRunStatus,
  isAwaitingApproval,
  isHitlDisabledError,
  STATUS_AWAITING_APPROVAL,
} from '../lib/hitl'
import { failureClassLabel } from '../lib/traceLabels'
import type { ExecutionTrace, RunArtifact, Task, TaskStep } from '../types/task'

export function TasksPage() {
  const workspace = getStoredWorkspace()
  const user = getStoredUser()
  if (!workspace?.id) return <Navigate to="/app" replace />
  return (
    <TasksPageInner
      workspaceId={workspace.id}
      role={workspace.role || 'owner'}
      userId={user?.id ?? null}
    />
  )
}

function TasksPageInner({
  workspaceId,
  role,
  userId,
}: {
  workspaceId: string
  role: string
  userId: string | null
}) {
  const [policyDeniedOnly, setPolicyDeniedOnly] = useState(false)
  const [awaitingOnly, setAwaitingOnly] = useState(false)
  const {
    data: listData,
    isLoading: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ['tasks', workspaceId, policyDeniedOnly, awaitingOnly],
    queryFn: () =>
      listTasks(workspaceId, {
        policy_denied: policyDeniedOnly ? true : undefined,
        status: awaitingOnly ? STATUS_AWAITING_APPROVAL : undefined,
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
  const [hitlError, setHitlError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [hitlBusy, setHitlBusy] = useState(false)

  const loadError = queryError instanceof Error ? queryError.message : null
  const displayError = error ?? loadError

  async function refreshList() {
    await refetch()
  }

  async function hydrateDetail(taskId: string) {
    const t = await getTask(workspaceId, taskId)
    const s = await getTaskSteps(workspaceId, taskId)
    setSelected(t)
    setSteps(s.items)
    try {
      setTrace(await getTaskExecution(workspaceId, taskId))
    } catch {
      setTrace(null)
    }
    try {
      const arts = await listTaskArtifacts(workspaceId, taskId)
      setArtifacts(arts.items)
    } catch {
      setArtifacts([])
    }
    return t
  }

  async function openTask(task: Task) {
    setError(null)
    setHitlError(null)
    setTrace(null)
    setArtifacts([])
    setSelectedArtifactId(null)
    setArtifactDetail(null)
    try {
      await hydrateDetail(task.id)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Load failed')
    }
  }

  const selectedId = selected?.id
  const selectedIsActive = selected ? isActiveRunStatus(selected.status) : false

  // Poll active selected runs (incl. awaiting_approval) — Tasks page has no SSE.
  useEffect(() => {
    if (!selectedId || !selectedIsActive) return
    const taskId = selectedId
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const t = await getTask(workspaceId, taskId)
          setSelected(t)
          const s = await getTaskSteps(workspaceId, taskId)
          setSteps(s.items)
          if (!isActiveRunStatus(t.status) || isAwaitingApproval(t.status)) {
            try {
              setTrace(await getTaskExecution(workspaceId, taskId))
            } catch {
              // ignore
            }
          }
          if (!isActiveRunStatus(t.status)) {
            await refetch()
          }
        } catch {
          // ignore transient
        }
      })()
    }, 1500)
    return () => window.clearInterval(id)
  }, [selectedId, selectedIsActive, workspaceId, refetch])

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
    setHitlError(null)
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

  async function onHitlApprove() {
    if (!selected) return
    setHitlBusy(true)
    setHitlError(null)
    try {
      const t = await approveTask(workspaceId, selected.id)
      setSelected(t)
      await refreshList()
    } catch (err) {
      if (err instanceof ApiError && isHitlDisabledError(err)) {
        setHitlError('SQL approval is disabled on the server (kill-switch off).')
      } else {
        setHitlError(err instanceof ApiError || err instanceof Error ? err.message : 'Approve failed')
      }
    } finally {
      setHitlBusy(false)
    }
  }

  async function onHitlReject(reason?: string) {
    if (!selected) return
    setHitlBusy(true)
    setHitlError(null)
    try {
      const t = await rejectTask(workspaceId, selected.id, reason ? { reason } : undefined)
      setSelected(t)
      await refreshList()
      try {
        setTrace(await getTaskExecution(workspaceId, t.id))
      } catch {
        // ignore
      }
    } catch (err) {
      if (err instanceof ApiError && isHitlDisabledError(err)) {
        setHitlError('SQL approval is disabled on the server (kill-switch off).')
      } else {
        setHitlError(err instanceof ApiError || err instanceof Error ? err.message : 'Reject failed')
      }
    } finally {
      setHitlBusy(false)
    }
  }

  const awaiting = selected ? isAwaitingApproval(selected.status) : false
  const hitlCanAct = selected ? canActOnHitl(selected, userId, role) : false
  const showCancel =
    selected != null &&
    (selected.status === 'pending' || selected.status === 'running')

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
            onChange={() => {
              setPolicyDeniedOnly((prev) => !prev)
              setError(null)
            }}
          />
          Show policy_denied only
        </label>
        <label className="filter-check">
          <input
            type="checkbox"
            checked={awaitingOnly}
            onChange={() => {
              setAwaitingOnly((prev) => !prev)
              setError(null)
            }}
          />
          Show awaiting approval only
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
                      <span className="caption">
                        {failureClassLabel(selected.failure_class)}
                      </span>
                    ) : null}
                    {selected.policy_denied ? (
                      <StatusBadge status="denied" label="policy denied" />
                    ) : null}
                  </div>
                  <p className="caption mono">{selected.id}</p>
                  <p className="run-panel__question">{selected.question}</p>

                  {showCancel ? (
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      loading={cancelling}
                      onClick={() => void onCancel()}
                    >
                      {cancelling ? 'Cancelling…' : 'Cancel run'}
                    </Button>
                  ) : null}

                  {awaiting ? (
                    <HitlApprovalPanel
                      task={selected}
                      canAct={hitlCanAct}
                      busy={hitlBusy || cancelling}
                      actionError={hitlError}
                      onApprove={onHitlApprove}
                      onReject={onHitlReject}
                      onCancel={onCancel}
                    />
                  ) : null}

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
