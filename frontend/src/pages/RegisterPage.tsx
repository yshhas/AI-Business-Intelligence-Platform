import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { register as registerApi } from '../api/auth'
import { Alert, Button, Card, CardBody, Input } from '../components/ui'
import { setSession } from '../stores/authStore'

export function RegisterPage() {
  const navigate = useNavigate()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await registerApi({
        email,
        password,
        display_name: displayName,
      })
      setSession(res.access_token, res.user, res.workspace, res.refresh_token)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-page">
      <Card className="auth-card">
        <CardBody className="auth-card__body">
          <header className="auth-card__header">
            <h1 className="auth-card__title">Create account</h1>
            <p className="auth-card__subtitle">
              Register to get a personal workspace and start analyzing data.
            </p>
          </header>

          <form className="auth-form" onSubmit={onSubmit}>
            <label className="field">
              <span className="field-label">Display name</span>
              <Input
                required
                autoComplete="name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Alex Chen"
              />
            </label>

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
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
              <span className="field-hint">Minimum 8 characters.</span>
            </label>

            {error ? <Alert variant="error">{error}</Alert> : null}

            <Button type="submit" variant="primary" block loading={loading}>
              {loading ? 'Creating…' : 'Create account'}
            </Button>
          </form>

          <p className="auth-card__footer">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </CardBody>
      </Card>
    </section>
  )
}
