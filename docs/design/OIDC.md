# OIDC Login (Wave 3 MVP)

Optional single-IdP Authorization Code flow. Disabled unless configured.

## Env

```
OIDC_ENABLED=true
OIDC_ISSUER=https://idp.example.com
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...   # optional for public clients
OIDC_REDIRECT_URI=http://localhost:5173/auth/oidc/callback
OIDC_SCOPES=openid email profile
```

## API

- `GET /api/v1/auth/oidc/login` → `{authorize_url, state}` (404 if disabled). State is stored in Redis (~10 min).
- `POST /api/v1/auth/oidc/callback` body `{code, state}` → same JWT pair as password login. Invalid/expired state → 400.

Discovery `authorization_endpoint` / `token_endpoint` / `userinfo_endpoint` must share the configured issuer host (SSRF guard).

Email from userinfo creates/links a local `User` with a random unusable password. No multi-IdP, no logout federation.
