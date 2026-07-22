export type Task = {
  id: string
  workspace_id: string
  dataset_id: string
  user_id: string
  question: string
  status: string
  result_json: Record<string, unknown> | null
  error_message: string | null
  cancel_requested?: boolean
  failure_class?: string | null
  timeout_seconds?: number | null
  skill_id?: string | null
  skill_version?: string | null
  source_type?: string | null
  policy_denied?: boolean
  llm_total_tokens?: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type TaskList = { items: Task[] }

export type TaskStep = {
  id: string
  task_id: string
  step_no: number
  node_name: string
  status: string
  input_json: Record<string, unknown> | null
  output_json: Record<string, unknown> | null
  error_message: string | null
  latency_ms: number | null
  created_at: string
}

export type StepList = { items: TaskStep[] }

export type ExecutionTrace = {
  run_id: string
  workspace_id: string
  dataset_id: string
  question: string
  status: string
  failure_class: string | null
  skill_id: string | null
  skill_version?: string | null
  source_type: string | null
  policy_denied: boolean
  run: Record<string, unknown> | null
  data_plane: Record<string, unknown> | null
  authorization?: Record<string, unknown> | null
  /** E1-AC / E2: Schema Linking Lite projection (audit only). */
  sql_quality?: Record<string, unknown> | null
  execution: {
    schema_version?: number
    tool_calls?: Array<Record<string, unknown>>
    policy_decisions?: Array<Record<string, unknown>>
    artifacts?: Array<Record<string, unknown>>
    summary?: Record<string, unknown>
  }
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export type RunArtifact = {
  id: string
  task_id: string
  workspace_id: string
  type: string
  status: string
  content_ref: Record<string, unknown>
  title: string | null
  skill_id: string | null
  created_at: string
  payload?: unknown
  lineage?: Record<string, unknown> | null
}

export type ArtifactList = { items: RunArtifact[] }
