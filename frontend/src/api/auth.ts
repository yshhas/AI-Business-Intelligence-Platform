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

export function fetchMe(): Promise<User> {
  return apiRequest<User>('/api/v1/auth/me')
}

export function listWorkspaces(): Promise<{ items: Workspace[] }> {
  return apiRequest<{ items: Workspace[] }>('/api/v1/workspaces')
}
