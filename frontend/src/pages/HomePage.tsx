import { Link } from 'react-router-dom'
import { isAuthenticated } from '../stores/authStore'

const WORKFLOW = [
  {
    step: '01',
    title: 'Dataset',
    description: 'Upload CSV/Excel or bind a read-only Postgres source into your workspace.',
  },
  {
    step: '02',
    title: 'Analyze',
    description: 'Ask a business question and run an async text-to-SQL analysis task.',
  },
  {
    step: '03',
    title: 'Tasks',
    description: 'Track run status, inspect steps, and revisit completed analyses.',
  },
  {
    step: '04',
    title: 'Artifacts',
    description: 'Review SQL, previews, charts, and reports produced by each run.',
  },
] as const

export function HomePage() {
  const authed = isAuthenticated()

  return (
    <section className="landing">
      <div className="landing-hero">
        <p className="landing-kicker">Enterprise Data Agent Platform</p>
        <h1 className="landing-title">企业级数据智能体平台</h1>
        <p className="landing-lead">
          Turn workspace data into trustworthy answers — from dataset to analysis,
          execution trace, and shareable artifacts.
        </p>
        <div className="landing-actions">
          {authed ? (
            <>
              <Link to="/app" className="btn btn--primary btn--lg">
                Open Dashboard
              </Link>
              <Link to="/app/analyze" className="btn btn--secondary btn--lg">
                Start analysis
              </Link>
            </>
          ) : (
            <>
              <Link to="/register" className="btn btn--primary btn--lg">
                Get Started
              </Link>
              <Link to="/login" className="btn btn--secondary btn--lg">
                Sign In
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="landing-workflow">
        <div className="landing-workflow__header">
          <h2 className="section-title">How it works</h2>
          <p className="landing-workflow__subtitle">
            A focused path from data to decision — no dashboard clutter.
          </p>
        </div>

        <ol className="landing-flow">
          {WORKFLOW.map((item, index) => (
            <li key={item.step} className="landing-flow__item">
              <div className="landing-flow__card">
                <span className="landing-flow__step">{item.step}</span>
                <h3 className="landing-flow__title">{item.title}</h3>
                <p className="landing-flow__desc">{item.description}</p>
              </div>
              {index < WORKFLOW.length - 1 ? (
                <div className="landing-flow__arrow" aria-hidden>
                  ↓
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
