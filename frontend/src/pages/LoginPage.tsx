import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { login as loginApi } from '../api/auth'
import { Alert, Button, Card, CardBody, Input } from '../components/ui'
import { setSession } from '../stores/authStore'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await loginApi({ email, password })
      setSession(res.access_token, res.user, res.workspace, res.refresh_token)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-page">
      <Card className="auth-card">
        <CardBody className="auth-card__body">
          <header className="auth-card__header">
            <h1 className="auth-card__title">Sign in</h1>
            <p className="auth-card__subtitle">
              Access your workspace and continue analysis where you left off.
            </p>
          </header>

          <form className="auth-form" onSubmit={onSubmit}>
            <label className="field">
              <span className="field-label">Email</span>
              <Input
                required
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </label>

            <label className="field">
              <span className="field-label">Password</span>
              <Input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </label>

            {error ? <Alert variant="error">{error}</Alert> : null}

            <Button type="submit" variant="primary" block loading={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <p className="auth-card__footer">
            No account? <Link to="/register">Create one</Link>
          </p>
        </CardBody>
      </Card>
    </section>
  )
}
