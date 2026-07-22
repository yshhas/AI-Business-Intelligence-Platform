import { getToken, clearSession } from '../stores/authStore'
import { ApiError } from './client'
import type { Task, TaskStep } from '../types/task'

/** Progress-safe step payload from SSE (may omit full input/output). */
export type TaskEventStep = Pick<
  TaskStep,
  'id' | 'task_id' | 'step_no' | 'node_name' | 'status' | 'latency_ms' | 'error_message' | 'created_at'
> & {
  output_json?: Record<string, unknown> | null
  input_json?: Record<string, unknown> | null
}

export type TaskEventBrief = Pick<
  Task,
  | 'id'
  | 'status'
  | 'failure_class'
  | 'skill_id'
  | 'skill_version'
  | 'error_message'
  | 'cancel_requested'
  | 'started_at'
  | 'finished_at'
>

export type TaskProgressEvent =
  | { event: 'snapshot'; data: { task: TaskEventBrief; steps: TaskEventStep[] } }
  | { event: 'step'; data: { step: TaskEventStep } }
  | { event: 'status'; data: { status: string; task: TaskEventBrief } }
  | { event: 'terminal'; data: { status: string; task: TaskEventBrief } }
  | { event: 'heartbeat'; data: { ts: number } }
  | { event: 'error'; data: { message: string } }

export type SubscribeTaskEventsOptions = {
  signal?: AbortSignal
  /** Last-Event-ID from prior SSE chunk (sent if backend supports resume). */
  lastEventId?: string | null
  onEvent: (ev: TaskProgressEvent) => void
  /** Called when the stream ends without terminal/error (disconnect). */
  onDisconnect?: () => void
}

const SSE_MAX_RECONNECT_ATTEMPTS = 5
const SSE_RECONNECT_BASE_MS = 500
const SSE_RECONNECT_MAX_MS = 8000

function parseSseBlock(block: string): { event: string; data: string; id?: string } | null {
  let eventName = 'message'
  let eventId: string | undefined
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  return { event: eventName, data: dataLines.join('\n'), id: eventId }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const timer = window.setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

/**
 * T-10: Subscribe to Analyze task progress via SSE (fetch + Bearer).
 * Not LLM token streaming. Returns last seen event id (if any).
 */
export async function subscribeTaskEvents(
  workspaceId: string,
  taskId: string,
  options: SubscribeTaskEventsOptions,
): Promise<'terminal' | 'disconnect'> {
  const headers = new Headers({ Accept: 'text/event-stream' })
  const token = getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (options.lastEventId) {
    headers.set('Last-Event-ID', options.lastEventId)
  }

  const res = await fetch(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/events`,
    { headers, signal: options.signal },
  )

  if (res.status === 401) {
    clearSession()
    throw new ApiError(401, 'Unauthorized')
  }
  if (!res.ok) {
    throw new ApiError(res.status, `SSE failed (${res.status})`)
  }
  if (!res.body) {
    throw new ApiError(500, 'SSE response has no body')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const parsed = parseSseBlock(part.trim())
      if (!parsed) continue
      let data: unknown
      try {
        data = JSON.parse(parsed.data)
      } catch {
        continue
      }
      options.onEvent({
        event: parsed.event,
        data,
      } as TaskProgressEvent)
      if (parsed.event === 'terminal' || parsed.event === 'error') {
        return 'terminal'
      }
    }
  }

  options.onDisconnect?.()
  return 'disconnect'
}

export type SubscribeTaskEventsWithReconnectOptions = Omit<
  SubscribeTaskEventsOptions,
  'lastEventId' | 'onDisconnect'
> & {
  /** Invoked after max reconnect attempts — caller should start polling. */
  onFallback?: () => void
}

/**
 * SSE with exponential backoff reconnect (max ~5 attempts) before poll fallback.
 */
export async function subscribeTaskEventsWithReconnect(
  workspaceId: string,
  taskId: string,
  options: SubscribeTaskEventsWithReconnectOptions,
): Promise<void> {
  let lastEventId: string | null = null
  let attempt = 0

  while (attempt <= SSE_MAX_RECONNECT_ATTEMPTS) {
    if (options.signal?.aborted) return
    try {
      const outcome = await subscribeTaskEvents(workspaceId, taskId, {
        signal: options.signal,
        lastEventId,
        onEvent: (ev) => {
          if (ev.event === 'step' && ev.data.step?.id) {
            lastEventId = ev.data.step.id
          } else if (ev.event === 'heartbeat') {
            lastEventId = String(ev.data.ts)
          }
          options.onEvent(ev)
        },
      })
      if (outcome === 'terminal') return
      // Unexpected disconnect — retry with backoff
    } catch (err) {
      if (options.signal?.aborted) return
      if (err instanceof ApiError && err.status === 401) throw err
    }

    attempt += 1
    if (attempt > SSE_MAX_RECONNECT_ATTEMPTS) break

    const delay = Math.min(
      SSE_RECONNECT_BASE_MS * 2 ** (attempt - 1),
      SSE_RECONNECT_MAX_MS,
    )
    try {
      await sleep(delay, options.signal)
    } catch {
      return
    }
  }

  options.onFallback?.()
}

export function stepFromEvent(step: TaskEventStep): TaskStep {
  return {
    id: step.id,
    task_id: step.task_id,
    step_no: step.step_no,
    node_name: step.node_name,
    status: step.status,
    input_json: step.input_json ?? null,
    output_json: step.output_json ?? null,
    error_message: step.error_message,
    latency_ms: step.latency_ms,
    created_at: step.created_at,
  }
}

export function mergeTaskBrief(task: Task, brief: TaskEventBrief): Task {
  return {
    ...task,
    status: brief.status,
    failure_class: brief.failure_class ?? task.failure_class,
    skill_id: brief.skill_id ?? task.skill_id,
    skill_version: brief.skill_version ?? task.skill_version,
    error_message: brief.error_message ?? task.error_message,
    cancel_requested: brief.cancel_requested ?? task.cancel_requested,
    started_at: brief.started_at ?? task.started_at,
    finished_at: brief.finished_at ?? task.finished_at,
  }
}
