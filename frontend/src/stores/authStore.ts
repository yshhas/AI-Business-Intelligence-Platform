import type { User, Workspace } from '../types/auth'

const TOKEN_KEY = 'aibi_access_token'
const REFRESH_KEY = 'aibi_refresh_token'
const USER_KEY = 'aibi_user'
const WORKSPACE_KEY = 'aibi_workspace'

function readJson<T>(key: string): T | null {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function getStoredUser(): User | null {
  return readJson<User>(USER_KEY)
}

export function getStoredWorkspace(): Workspace | null {
  return readJson<Workspace>(WORKSPACE_KEY)
}

export function setSession(
  token: string,
  user: User,
  workspace: Workspace | null,
  refreshToken?: string | null,
): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken)
  }
  if (workspace) {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace))
  } else {
    localStorage.removeItem(WORKSPACE_KEY)
  }
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_KEY, refreshToken)
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(WORKSPACE_KEY)
}

export function isAuthenticated(): boolean {
  return Boolean(getToken())
}
