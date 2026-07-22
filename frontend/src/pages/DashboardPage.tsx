import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listWorkspaces } from '../api/auth'
import { ApiError } from '../api/client'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  PageHeader,
  SpinnerBlock,
} from '../components/ui'
import { getStoredUser, getStoredWorkspace } from '../stores/authStore'

/** Post-login product home. */
export function DashboardPage() {
  const user = getStoredUser()
  const storedWs = getStoredWorkspace()
  const {
    data: wsData,
    isLoading: loading,
    error: queryError,
  } = useQuery({
    queryKey: ['workspaces'],
    queryFn: () => listWorkspaces(),
  })
  const workspaces = wsData?.items ?? (storedWs ? [storedWs] : [])
  const error =
    queryError instanceof ApiError
      ? queryError.message
      : queryError instanceof Error
        ? queryError.message
        : null

  const primary = workspaces[0]

  return (
    <section className="workspace-page">
      <PageHeader
        title={`Welcome${user?.display_name ? `, ${user.display_name}` : ''}`}
        description="Your workspace hub for datasets, analysis runs, and task history."
      />

      {error ? <Alert variant="error">{error}</Alert> : null}

      {loading ? (
        <SpinnerBlock label="Loading workspace…" />
      ) : (
        <>
          <div className="dashboard-grid">
            <Card>
              <CardHeader
                title="Workspace overview"
                description="Primary workspace bound to your current session."
              />
              <CardBody>
                {primary ? (
                  <div className="stack-sm">
                    <div className="meta-row">
                      <strong>{primary.name}</strong>
                      <Badge variant="neutral">{primary.role}</Badge>
                    </div>
                    <p className="caption">
                      Signed in as {user?.email ?? '—'}
                    </p>
                    <p className="caption mono">id: {primary.id}</p>
                    {workspaces.length > 1 ? (
                      <p className="caption">
                        {workspaces.length} workspaces available in this account.
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <EmptyState
                    title="No workspace found"
                    description="Your account does not have a workspace yet. Re-register or contact support."
                  />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Session"
                description="Continue the Dataset → Analyze → Tasks workflow."
              />
              <CardBody>
                <div className="stack-sm">
                  <p className="body-text">
                    Upload or bind data, run text-to-SQL analysis, then inspect
                    traces and artifacts in task history.
                  </p>
                  <div className="meta-row">
                    <Badge variant="info">JWT session</Badge>
                    <span className="caption">Token stored in localStorage</span>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>

          <div>
            <h2 className="workspace-section-title">Quick actions</h2>
            <div className="quick-actions">
              <Link to="/app/datasets" className="quick-action">
                <span className="quick-action__title">Datasets</span>
                <span className="quick-action__desc">
                  Upload CSV/Excel or bind a read-only Postgres source.
                </span>
              </Link>
              <Link to="/app/analyze" className="quick-action">
                <span className="quick-action__title">Analyze</span>
                <span className="quick-action__desc">
                  Ask a question and start an async analysis run.
                </span>
              </Link>
              <Link to="/app/tasks" className="quick-action">
                <span className="quick-action__title">Tasks</span>
                <span className="quick-action__desc">
                  Review run history, steps, and produced artifacts.
                </span>
              </Link>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
