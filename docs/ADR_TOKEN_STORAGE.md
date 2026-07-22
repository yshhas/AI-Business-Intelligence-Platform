# ADR: Token Storage Strategy (P1.8)

**Status:** Accepted for **v1.1**  
**Date:** 2026-07-22  
**Deciders:** Sprint 4 Design Review (approved)  

---

## Context

The Product Shell stores JWT **access** and **refresh** tokens in browser `localStorage` (`frontend/src/stores/authStore.ts`). Enterprise reviewers often ask for HttpOnly Cookie storage to reduce XSS token theft.

Sprint 2 delivered **refresh `jti` revoke / rotation** (`refresh_sessions`). Access tokens remain short-lived and stateless.

## Decision

For **v1.1**, we **accept localStorage** for access + refresh tokens and ship **documentation only** (this ADR).

We **do not** implement HttpOnly Cookie / CSRF-protected cookie session in v1.1.

## Acceptance conditions (v1.1)

| Control | Requirement | Status |
|---------|-------------|--------|
| Access TTL | Short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default **30**) | In place |
| Refresh TTL | Bounded (`REFRESH_TOKEN_EXPIRE_MINUTES`, default **10080** = 7d) | In place |
| Refresh revoke | Rotation invalidates prior `jti`; logout revokes current session | In place (P1.2) |
| Multi-device | Multiple refresh sessions allowed; logout = current device | In place |
| XSS residual | Accepted risk for pilot; mitigate via normal XSS hygiene (no `eval` of untrusted HTML, dependency updates) | Accepted |
| Cookie MVP | Explicitly **out of scope** for v1.1 | This ADR |

## Why Cookie is deferred

1. **CSRF**: Cookie auth requires SameSite + CSRF tokens or double-submit patterns across SPA + API origins.  
2. **CORS / cross-site**: Current SPA often runs on `:5173` with API `:8000` — cookie domain/`credentials` wiring is non-trivial.  
3. **Refresh flow rewrite**: FE and auth routes must move off `Authorization`/`localStorage` refresh body.  
4. **Revoke already exists**: Highest trust gap (unrevocable refresh) was closed in Sprint 2 without Cookie complexity.

## Consequences

- **Positive:** v1.1 ships without auth UX rewrite risk; revoke story is complete for refresh.  
- **Negative:** XSS can still steal tokens until Cookie migration.  
- **Neutral:** Access tokens expire quickly; stolen refresh can be revoked via logout / rotation.

## Future Cookie migration triggers

Revisit Cookie (or BFF) when **any** of:

1. Production threat model requires HttpOnly as a hard gate (customer/security review).  
2. First-party same-site deploy (API + UI shared origin) makes Cookie+CSRF cheap.  
3. Formal penetration test flags localStorage as critical with no compensating control accepted.

Until then, keep P1.2 revoke + short access TTL as the primary session controls.

## Related

- `docs/API_ERROR_CODES.md` — auth/refresh/logout  
- Sprint 2 refresh_sessions  
- Non-goal: Phase 2 HITL, Semantic Layer, Multi-Agent unrelated to this ADR  
