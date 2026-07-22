import { apiRequest } from './client'
import type { AuthResponse, TokenRefreshResponse, User, Workspace } from '../types/auth'

export function register(payload: {
  email: string
  password: string
  display_name: string
}): Promise<AuthResponse> {
  return apiRequest<AuthResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: payload,
    auth: false,
  })
}

export function login(payload: { email: string; password: string }): Promise<AuthResponse> {
  return apiRequest<AuthResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: payload,
    auth: false,
  })
}

export function refreshTokens(refreshToken: string): Promise<TokenRefreshResponse> {
  return apiRequest<TokenRefreshResponse>('/api/v1/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
    auth: false,
  })
}

/** Best-effort server revoke of the current refresh session (P1.2). */
export async function logout(refreshToken: string | null | undefined): Promise<void> {
  if (!refreshToken) return
  try {
    await apiRequest<void>('/api/v1/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      auth: false,
    })
  } catch {
    // Client still clears local session even if revoke fails.
  }
}

export function fetchMe(): Promise<User> {
  return apiRequest<User>('/api/v1/auth/me')
}

export function listWorkspaces(): Promise<{ items: Workspace[] }> {
  return apiRequest<{ items: Workspace[] }>('/api/v1/workspaces')
}
