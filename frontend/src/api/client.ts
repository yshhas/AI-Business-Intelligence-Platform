import {
  clearSession,
  getRefreshToken,
  getToken,
  setTokens,
} from '../stores/authStore'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  auth?: boolean
  /** Internal: skip refresh retry to avoid loops */
  _retried?: boolean
}

let refreshInFlight: Promise<boolean> | null = null

async function tryRefreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!res.ok) return false
        const data = (await res.json()) as {
          access_token: string
          refresh_token: string
        }
        setTokens(data.access_token, data.refresh_token)
        return true
      } catch {
        return false
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (options.auth !== false) {
    const token = getToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  const res = await fetch(path, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })

  if (res.status === 401 && options.auth !== false && !options._retried) {
    const refreshed = await tryRefreshSession()
    if (refreshed) {
      return apiRequest<T>(path, { ...options, _retried: true })
    }
    clearSession()
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string | { msg?: string }[] }
      if (typeof data.detail === 'string') {
        detail = data.detail
      } else if (Array.isArray(data.detail) && data.detail[0]?.msg) {
        detail = data.detail[0].msg
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}
