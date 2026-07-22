export type SchemaColumn = {
  name: string
  type: string
}

export type Dataset = {
  id: string
  workspace_id: string
  name: string
  source_type: string
  original_filename: string
  duckdb_table: string
  schema_json: SchemaColumn[]
  row_count: number
  status: string
  source_config_json?: Record<string, unknown>
  created_by: string
  created_at: string
}

export type DatasetList = {
  items: Dataset[]
}

export type Preview = {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
}
