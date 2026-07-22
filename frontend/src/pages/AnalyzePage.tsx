import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { listDatasets } from '../api/datasets'
import {
  createTask,
  getTask,
  getTaskSteps,
  getTaskExecution,
  listTaskArtifacts,
  getTaskArtifact,
  cancelTask,
} from '../api/tasks'
import {
  mergeTaskBrief,
  stepFromEvent,
  subscribeTaskEventsWithReconnect,
} from '../api/taskEvents'
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
  PageHeader,
  Select,
  StatusBadge,
  Textarea,
} from '../components/ui'
import { getStoredWorkspace } from '../stores/authStore'
import {
  failureClassLabel,
  friendlySubmitError,
  nodeLabel,
} from '../lib/traceLabels'
import type { Dataset } from '../types/dataset'
import type { ExecutionTrace, RunArtifact, Task, TaskStep } from '../types/task'

export function AnalyzePage() {
  const workspace = getStoredWorkspace()
  if (!workspace?.id) return <Navigate to="/app" replace />
  return (
    <AnalyzePageInner
      workspaceId={workspace.id}
      workspaceName={workspace.name}
      role={workspace.role || 'owner'}
    />
  )
}

function AnalyzePageInner({
  workspaceId,
  workspaceName,
  role,
}: {
  workspaceId: string
  workspaceName: string
  role: string
}) {
  const canRun = role === 'owner' || role === 'analyst'
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState('')
  const [skillId, setSkillId] = useState<'data.bi' | 'data.profile'>('data.bi')
  const [question, setQuestion] = useState('')
  const [task, setTask] = useState<Task | null>(null)
  const [steps, setSteps] = useState<TaskStep[]>([])
  const [trace, setTrace] = useState<ExecutionTrace | null>(null)
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([])
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [artifactDetail, setArtifactDetail] = useState<RunArtifact | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await listDatasets(workspaceId)
        if (cancelled) return
        const ready = res.items.filter((d) => d.status === 'ready')
        setDatasets(ready)
        if (ready[0]) setDatasetId(ready[0].id)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load datasets')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  // T-10: SSE progress while pending/running; poll fallback if SSE fails
  useEffect(() => {
    if (!task?.id) return
    const taskId = task.id
    let cancelled = false
    let pollId: number | null = null
    const ac = new AbortController()

    async function loadTerminalExtras() {
      try {
        const t = await getTask(workspaceId, taskId)
        if (!cancelled) setTask(t)
      } catch {
        // ignore
      }
      try {
        const ex = await getTaskExecution(workspaceId, taskId)
        if (!cancelled) setTrace(ex)
      } catch {
        // ignore if trace not ready
      }
      try {
        const arts = await listTaskArtifacts(workspaceId, taskId)
        if (!cancelled) setArtifacts(arts.items)
      } catch {
        // ignore if artifacts not ready
      }
    }

    function startPollFallback() {
      if (pollId != null || cancelled) return
      pollId = window.setInterval(async () => {
        try {
          const t = await getTask(workspaceId, taskId)
          if (cancelled) return
          setTask(t)
          const s = await getTaskSteps(workspaceId, taskId)
          if (cancelled) return
          setSteps(s.items)
          if (t.status !== 'pending' && t.status !== 'running') {
            await loadTerminalExtras()
          }
        } catch {
          // ignore transient poll errors
        }
      }, 1000)
    }

    ;(async () => {
      // Fresh status check — avoids capturing task.status in effect deps (oxlint).
      try {
        const latest = await getTask(workspaceId, taskId)
        if (cancelled) return
        if (latest.status !== 'pending' && latest.status !== 'running') {
          setTask(latest)
          return
        }
      } catch {
        return
      }
      try {
        await subscribeTaskEventsWithReconnect(workspaceId, taskId, {
          signal: ac.signal,
          onEvent: (ev) => {
            if (cancelled) return
            if (ev.event === 'snapshot') {
              setTask((prev) => (prev ? mergeTaskBrief(prev, ev.data.task) : prev))
              setSteps(ev.data.steps.map(stepFromEvent))
            } else if (ev.event === 'step') {
              const next = stepFromEvent(ev.data.step)
              setSteps((prev) => {
                const without = prev.filter((s) => s.step_no !== next.step_no)
                return [...without, next].sort((a, b) => a.step_no - b.step_no)
              })
            } else if (ev.event === 'status') {
              setTask((prev) => (prev ? mergeTaskBrief(prev, ev.data.task) : prev))
            } else if (ev.event === 'terminal') {
              setTask((prev) => (prev ? mergeTaskBrief(prev, ev.data.task) : prev))
              void loadTerminalExtras()
            } else if (ev.event === 'error') {
              startPollFallback()
            }
          },
          onFallback: () => {
            if (!cancelled && !ac.signal.aborted) {
              startPollFallback()
            }
          },
        })
      } catch {
        if (!cancelled && !ac.signal.aborted) {
          startPollFallback()
        }
      }
    })()

    return () => {
      cancelled = true
      ac.abort()
      if (pollId != null) window.clearInterval(pollId)
    }
    // Only re-subscribe when the Run id changes (not on every status patch from SSE).
  }, [task?.id, workspaceId])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canRun) {
      setError('Insufficient role: viewer cannot create analysis runs')
      return
    }
    if (!datasetId || !question.trim()) {
      setError('Select a ready dataset and enter a question')
      return
    }
    setSubmitting(true)
    setError(null)
    setSteps([])
    setTrace(null)
    setArtifacts([])
    setSelectedArtifactId(null)
    setArtifactDetail(null)
    try {
      const t = await createTask(workspaceId, {
        dataset_id: datasetId,
        question: question.trim(),
        skill_id: skillId,
      })
      setTask(t)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(friendlySubmitError(err))
      } else {
        setError(err instanceof Error ? err.message : 'Submit failed')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function onSelectArtifact(id: string) {
    if (!task) return
    setSelectedArtifactId(id)
    try {
      const d = await getTaskArtifact(workspaceId, task.id, id)
      setArtifactDetail(d)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Artifact load failed')
    }
  }

  async function onCancel() {
    if (!task) return
    setCancelling(true)
    setError(null)
    try {
      const t = await cancelTask(workspaceId, task.id)
      setTask(t)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Cancel failed')
    } finally {
      setCancelling(false)
    }
  }

  const isRunning = task?.status === 'pending' || task?.status === 'running'

  return (
    <section className="workspace-page">
      <PageHeader
        title="Analyze"
        description={
          <>
            Text-to-SQL command center. Workspace <strong>{workspaceName}</strong> · role{' '}
            <code className="mono">{role}</code>
            {!canRun ? ' · viewer cannot create runs' : null}
          </>
        }
      />

      {!canRun ? (
        <Alert variant="warning">Your role cannot create analysis runs.</Alert>
      ) : null}

      <Card className={!canRun ? 'analyze-command is-disabled' : 'analyze-command'}>
        <CardHeader
          title="Ask a question"
          description="Select a ready dataset and skill, describe what you need, then start a run."
        />
        <CardBody>
          <form className="stack" onSubmit={onSubmit}>
            <label className="field">
              <span className="field-label">Dataset (ready only)</span>
              <Select
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
                disabled={!canRun}
              >
                {datasets.length === 0 && <option value="">No ready datasets</option>}
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} [{d.source_type}] ({d.row_count} rows)
                  </option>
                ))}
              </Select>
            </label>
            <label className="field">
              <span className="field-label">Skill</span>
              <Select
                value={skillId}
                onChange={(e) =>
                  setSkillId(e.target.value === 'data.profile' ? 'data.profile' : 'data.bi')
                }
                disabled={!canRun}
              >
                <option value="data.bi">data.bi — Text-to-SQL analysis</option>
                <option value="data.profile">data.profile — Dataset profiling</option>
              </Select>
            </label>
            <label className="field">
              <span className="field-label">Question</span>
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                placeholder={
                  skillId === 'data.profile'
                    ? 'e.g. Profile this dataset'
                    : 'e.g. Rank regions by total sales'
                }
                disabled={!canRun}
              />
            </label>
            <div className="analyze-command__actions">
              <Button
                type="submit"
                loading={submitting}
                disabled={submitting || !datasetId || !canRun}
              >
                {submitting ? 'Submitting…' : 'Start analysis'}
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}

      {task ? (
        <Card>
          <CardBody>
            <div className="run-panel">
              <div className="run-panel__header">
                <div className="stack-sm">
                  <div className="meta-row">
                    <StatusBadge status={task.status} />
                    {task.failure_class ? (
                      <span className="caption">
                        {failureClassLabel(task.failure_class)}
                      </span>
                    ) : null}
                    {isRunning ? (
                      <span className="caption">Live progress via SSE</span>
                    ) : null}
                  </div>
                  <p className="run-panel__question">{task.question}</p>
                </div>
                {isRunning ? (
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
              </div>

              <div className="run-status-bar">
                <code>{task.id}</code>
                {task.skill_id ? (
                  <span>
                    skill <code>{task.skill_id}</code>
                    {task.skill_version ? <>@{task.skill_version}</> : null}
                  </span>
                ) : null}
                {task.source_type ? (
                  <span>
                    plane <code>{task.source_type}</code>
                  </span>
                ) : null}
                {task.llm_total_tokens != null ? (
                  <span>
                    tokens <code>{task.llm_total_tokens}</code>
                  </span>
                ) : null}
                {task.timeout_seconds != null ? (
                  <span>timeout {task.timeout_seconds}s</span>
                ) : null}
              </div>

              {task.error_message ? (
                <Alert variant="error">{task.error_message}</Alert>
              ) : null}

              <div className="section-block">
                <h3 className="section-block__title">Execution steps</h3>
                <p className="caption">
                  Task/steps progress only — not token streaming.
                </p>
                {steps.length === 0 ? (
                  <p className="caption">
                    {isRunning ? 'Waiting for worker…' : 'No steps recorded.'}
                  </p>
                ) : (
                  <ol className="step-list">
                    {steps.map((s) => (
                      <StepItem key={s.id} step={s} />
                    ))}
                  </ol>
                )}
              </div>

              <div className="section-block">
                <h3 className="section-block__title">Trace</h3>
                <ExecutionTracePanel
                  trace={trace}
                  steps={steps}
                  llmTotalTokens={task.llm_total_tokens}
                />
                {!trace ? (
                  <p className="caption">
                    {isRunning
                      ? 'Trace will appear when the run reaches a terminal state.'
                      : 'No execution trace for this run.'}
                  </p>
                ) : null}
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
                  resultJson={task.result_json}
                  llmTotalTokens={task.llm_total_tokens}
                />
              </div>

              <p className="caption">
                <Link to="/app/tasks">Open task history →</Link>
              </p>
            </div>
          </CardBody>
        </Card>
      ) : null}
    </section>
  )
}

function StepItem({ step }: { step: TaskStep }) {
  const [open, setOpen] = useState(false)
  const expandable =
    step.node_name === 'link_schema' ||
    step.node_name === 'validate_sql' ||
    step.node_name === 'generate_sql'
  const out = step.output_json || {}
  const inp = step.input_json || {}

  return (
    <li className="step-item">
      <div className="step-item__row">
        <span className="step-item__no">{step.step_no}.</span>
        <span className="step-item__name">{nodeLabel(step.node_name)}</span>
        <code className="step-item__code">{step.node_name}</code>
        <StatusBadge status={step.status} />
        {step.latency_ms != null ? (
          <span className="caption">{step.latency_ms}ms</span>
        ) : null}
        {expandable ? (
          <button
            type="button"
            className="step-item__toggle"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? 'Hide' : 'Details'}
          </button>
        ) : null}
      </div>
      {step.error_message ? (
        <div className="step-item__error">{step.error_message}</div>
      ) : null}
      {expandable && open ? (
        <pre className="code-block">
          {JSON.stringify(
            {
              input: briefObj(inp),
              output: briefObj(out),
            },
            null,
            2,
          )}
        </pre>
      ) : null}
    </li>
  )
}

function briefObj(data: Record<string, unknown>): Record<string, unknown> {
  const keys = [
    'link_status',
    'link_method',
    'link_reason',
    'selected_columns',
    'selected_tables',
    'column_count_full',
    'column_count_linked',
    'sql_draft',
    'sql_final',
    'question',
    'gate_error',
    'tool_id',
    'policy_id',
  ]
  const out: Record<string, unknown> = {}
  for (const k of keys) {
    if (k in data) out[k] = data[k]
  }
  if (Object.keys(out).length === 0) {
    return Object.fromEntries(Object.entries(data).slice(0, 6))
  }
  return out
}
