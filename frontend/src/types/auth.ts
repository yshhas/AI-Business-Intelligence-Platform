export type User = {
  id: string
  email: string
  display_name: string
  created_at: string
}

export type Workspace = {
  id: string
  name: string
  role: string
  created_at: string
  owner_user_id?: string
}

export type AuthResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
  workspace: Workspace | null
}

export type TokenRefreshResponse = {
  access_token: string
  refresh_token: string
  token_type: string
}
