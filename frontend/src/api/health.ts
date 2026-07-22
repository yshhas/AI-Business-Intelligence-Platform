export type HealthResponse = {
  status: string
  app?: string
  env?: string
}

/**
 * Phase 0: hit Vite proxy `/health` (same origin).
 * Later phases will use `/api/v1/...`.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/health')
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`)
  }
  return res.json() as Promise<HealthResponse>
}
