import { apiRequest } from './client'
import type { ArtifactList, ExecutionTrace, RunArtifact, StepList, Task, TaskList } from '../types/task'

export function createTask(
  workspaceId: string,
  body: { dataset_id: string; question: string; skill_id?: string },
): Promise<Task> {
  return apiRequest<Task>(`/api/v1/workspaces/${workspaceId}/tasks`, {
    method: 'POST',
    body,
  })
}

export type TaskListFilters = {
  limit?: number
  status?: string
  skill_id?: string
  source_type?: string
  policy_denied?: boolean
  failure_class?: string
}

export function listTasks(
  workspaceId: string,
  filters: TaskListFilters = {},
): Promise<TaskList> {
  const params = new URLSearchParams()
  params.set('limit', String(filters.limit ?? 50))
  if (filters.status) params.set('status', filters.status)
  if (filters.skill_id) params.set('skill_id', filters.skill_id)
  if (filters.source_type) params.set('source_type', filters.source_type)
  if (filters.policy_denied != null) {
    params.set('policy_denied', String(filters.policy_denied))
  }
  if (filters.failure_class) params.set('failure_class', filters.failure_class)
  return apiRequest<TaskList>(
    `/api/v1/workspaces/${workspaceId}/tasks?${params.toString()}`,
  )
}

export function getTask(workspaceId: string, taskId: string): Promise<Task> {
  return apiRequest<Task>(`/api/v1/workspaces/${workspaceId}/tasks/${taskId}`)
}

export function getTaskExecution(
  workspaceId: string,
  taskId: string,
): Promise<ExecutionTrace> {
  return apiRequest<ExecutionTrace>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/execution`,
  )
}

export function listTaskArtifacts(
  workspaceId: string,
  taskId: string,
  type?: string,
): Promise<ArtifactList> {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  const q = params.toString()
  return apiRequest<ArtifactList>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/artifacts${q ? `?${q}` : ''}`,
  )
}

export function getTaskArtifact(
  workspaceId: string,
  taskId: string,
  artifactId: string,
): Promise<RunArtifact> {
  return apiRequest<RunArtifact>(
    `/api/v1/workspaces/${workspaceId}/tasks/${taskId}/artifacts/${artifactId}`,
  )
}

export function getTaskSteps(workspaceId: string, taskId: string): Promise<StepList> {
  return apiRequest<StepList>(`/api/v1/workspaces/${workspaceId}/tasks/${taskId}/steps`)
}

export function cancelTask(workspaceId: string, taskId: string): Promise<Task> {
  return apiRequest<Task>(`/api/v1/workspaces/${workspaceId}/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
}
