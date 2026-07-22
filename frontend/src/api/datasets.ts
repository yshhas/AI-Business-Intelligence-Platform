import { apiRequest } from './client'
import type { Dataset, DatasetList, Preview } from '../types/dataset'

export function listDatasets(workspaceId: string): Promise<DatasetList> {
  return apiRequest<DatasetList>(`/api/v1/workspaces/${workspaceId}/datasets`)
}

export function getDataset(workspaceId: string, datasetId: string): Promise<Dataset> {
  return apiRequest<Dataset>(`/api/v1/workspaces/${workspaceId}/datasets/${datasetId}`)
}

export function previewDataset(
  workspaceId: string,
  datasetId: string,
  limit = 50,
): Promise<Preview> {
  return apiRequest<Preview>(
    `/api/v1/workspaces/${workspaceId}/datasets/${datasetId}/preview?limit=${limit}`,
  )
}

export async function uploadDataset(
  workspaceId: string,
  file: File,
  name?: string,
): Promise<Dataset> {
  const token = localStorage.getItem('aibi_access_token')
  const form = new FormData()
  form.append('file', file)
  if (name) form.append('name', name)

  const res = await fetch(`/api/v1/workspaces/${workspaceId}/datasets/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  })

  if (!res.ok) {
    let detail = `Upload failed (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string }
      if (typeof data.detail === 'string') detail = data.detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return (await res.json()) as Dataset
}

export function bindPostgresRoDataset(
  workspaceId: string,
  body: { name: string; tables: string[] },
): Promise<Dataset> {
  return apiRequest<Dataset>(`/api/v1/workspaces/${workspaceId}/datasets/postgres-ro`, {
    method: 'POST',
    body,
  })
}
