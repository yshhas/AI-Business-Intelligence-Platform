import { Navigate, Outlet } from 'react-router-dom'
import { isAuthenticated } from '../stores/authStore'

export function RequireAuth() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}
