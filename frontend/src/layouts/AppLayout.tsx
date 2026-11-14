import { useEffect, useId, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { logout as logoutApi } from '../api/auth'
import { Button } from '../components/ui'
import {
  clearSession,
  getRefreshToken,
  getStoredUser,
  getStoredWorkspace,
  isAuthenticated,
} from '../stores/authStore'

function navClassName({ isActive }: { isActive: boolean }): string {
  return isActive ? 'app-nav-link is-active' : 'app-nav-link'
}

/**
 * Phase 2: sticky header, active nav, mobile menu, page fade.
 * Auth/logout and route targets are unchanged from Phase 1.
 */
export function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const menuId = useId()
  const [menuOpen, setMenuOpen] = useState(false)

  const authed = isAuthenticated()
  const user = getStoredUser()
  const workspace = getStoredWorkspace()
  const wideMain = location.pathname.startsWith('/app/analyze')

  async function logout() {
    const refresh = getRefreshToken()
    await logoutApi(refresh)
    clearSession()
    setMenuOpen(false)
    navigate('/login', { replace: true })
  }

  function closeMenu() {
    setMenuOpen(false)
  }

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!menuOpen) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  const navLinks = authed ? (
    <>
      <NavLink to="/" end className={navClassName} onClick={closeMenu}>
        Overview
      </NavLink>
      <NavLink to="/app" end className={navClassName} onClick={closeMenu}>
        Dashboard
      </NavLink>
      <NavLink to="/app/datasets" className={navClassName} onClick={closeMenu}>
        Datasets
      </NavLink>
      <NavLink to="/app/analyze" className={navClassName} onClick={closeMenu}>
        Analyze
      </NavLink>
      <NavLink to="/app/tasks" className={navClassName} onClick={closeMenu}>
        Tasks
      </NavLink>
    </>
  ) : (
    <>
      <NavLink to="/" end className={navClassName} onClick={closeMenu}>
        Overview
      </NavLink>
      <NavLink to="/login" className={navClassName} onClick={closeMenu}>
        Login
      </NavLink>
      <NavLink to="/register" className={navClassName} onClick={closeMenu}>
        Register
      </NavLink>
    </>
  )

  return (
    <div className="app-shell">
      <header className="app-header">
        <LinkBrand />

        <nav className="app-nav app-nav--desktop" aria-label="Primary">
          {navLinks}
        </nav>

        <div className="app-header-meta">
          <span className="app-user-capsule" title={authed ? undefined : 'Guest'}>
            {authed ? (
              <>
                <span className="app-user-capsule__name">
                  {user?.display_name ?? 'User'}
                </span>
                <span className="app-user-capsule__sep" aria-hidden>
                  ·
                </span>
                <span className="app-user-capsule__ws">
                  {workspace?.name ?? 'Workspace'}
                </span>
              </>
            ) : (
              'Guest'
            )}
          </span>

          {authed ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="app-logout-btn"
              onClick={logout}
            >
              Logout
            </Button>
          ) : null}

          <button
            type="button"
            className="app-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="app-menu-toggle__bars" aria-hidden>
              <span />
              <span />
              <span />
            </span>
          </button>
        </div>
      </header>

      <div
        id={menuId}
        className={menuOpen ? 'app-mobile-panel is-open' : 'app-mobile-panel'}
        hidden={!menuOpen}
      >
        <nav className="app-nav app-nav--mobile" aria-label="Mobile">
          {navLinks}
        </nav>
        {authed ? (
          <div className="app-mobile-panel__meta">
            <span className="app-user-capsule app-user-capsule--mobile">
              <span className="app-user-capsule__name">
                {user?.display_name ?? 'User'}
              </span>
              <span className="app-user-capsule__sep" aria-hidden>
                ·
              </span>
              <span className="app-user-capsule__ws">
                {workspace?.name ?? 'Workspace'}
              </span>
            </span>
            <Button type="button" variant="secondary" size="sm" onClick={logout}>
              Logout
            </Button>
          </div>
        ) : null}
      </div>

      {menuOpen ? (
        <button
          type="button"
          className="app-mobile-backdrop"
          aria-label="Close menu"
          onClick={closeMenu}
        />
      ) : null}

      <main className={wideMain ? 'app-main app-main--wide' : 'app-main'}>
        <div key={location.pathname} className="page-enter">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function LinkBrand() {
  return (
    <NavLink to="/" end className="app-brand">
      <span className="app-brand-mark" aria-hidden />
      <span className="app-brand-text">企业级数据智能体平台</span>
    </NavLink>
  )
}
