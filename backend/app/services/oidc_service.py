"""OIDC login MVP (Wave 3) — one IdP, optional when OIDC_* env configured.

Authorization Code + token exchange via discovery; maps email → local User + JWT pair.
Not a full SSO product (no RP-initiated logout, no multi-IdP).

Stabilization: discovery endpoints must share issuer host (SSRF guard);
OAuth `state` stored in Redis; SSO accounts get random unusable passwords.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_token_pair, hash_password
from app.models import User
from app.services import workspace_service
from app.services.queue import get_redis

logger = logging.getLogger("app.oidc")

_STATE_TTL_SECONDS = 600


class OidcError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def oidc_configured(settings: Settings) -> bool:
    return bool(
        settings.oidc_enabled
        and (settings.oidc_issuer or "").strip()
        and (settings.oidc_client_id or "").strip()
        and (settings.oidc_redirect_uri or "").strip()
    )


def _issuer_host(settings: Settings) -> str:
    parsed = urlparse(settings.oidc_issuer.rstrip("/"))
    host = (parsed.hostname or "").lower()
    if not host:
        raise OidcError("OIDC issuer has no host", status_code=502)
    return host


def _assert_endpoint_on_issuer(settings: Settings, url: str, *, label: str) -> str:
    """Reject discovery endpoints that do not share the configured issuer host (SSRF)."""
    raw = (url or "").strip()
    if not raw:
        raise OidcError(f"OIDC discovery missing {label}", status_code=502)
    parsed = urlparse(raw)
    if parsed.scheme not in {"https", "http"}:
        raise OidcError(f"OIDC {label} must be http(s)", status_code=502)
    host = (parsed.hostname or "").lower()
    issuer_host = _issuer_host(settings)
    if host != issuer_host and not host.endswith(f".{issuer_host}"):
        raise OidcError(
            f"OIDC {label} host {host!r} does not match issuer {issuer_host!r}",
            status_code=502,
        )
    return raw


def _discovery(settings: Settings) -> dict[str, Any]:
    issuer = settings.oidc_issuer.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise OidcError(f"OIDC discovery failed: {exc}", status_code=502) from exc
    auth = _assert_endpoint_on_issuer(
        settings, str(data.get("authorization_endpoint") or ""), label="authorization_endpoint"
    )
    token = _assert_endpoint_on_issuer(
        settings, str(data.get("token_endpoint") or ""), label="token_endpoint"
    )
    out = dict(data)
    out["authorization_endpoint"] = auth
    out["token_endpoint"] = token
    if data.get("userinfo_endpoint"):
        out["userinfo_endpoint"] = _assert_endpoint_on_issuer(
            settings, str(data.get("userinfo_endpoint")), label="userinfo_endpoint"
        )
    return out


def store_oauth_state(state: str) -> None:
    if not state:
        raise OidcError("OIDC state required", status_code=400)
    try:
        get_redis().setex(f"aibi:oidc:state:{state}", _STATE_TTL_SECONDS, "1")
    except Exception as exc:  # noqa: BLE001
        raise OidcError(f"OIDC state store failed: {exc}", status_code=503) from exc


def consume_oauth_state(state: str | None) -> None:
    if not state or not str(state).strip():
        raise OidcError("OIDC state required", status_code=400)
    key = f"aibi:oidc:state:{str(state).strip()}"
    try:
        client = get_redis()
        ok = client.getdel(key) if hasattr(client, "getdel") else None
        if ok is None:
            # redis-py <4.2 fallback
            pipe = client.pipeline()
            pipe.get(key)
            pipe.delete(key)
            raw, _n = pipe.execute()
            ok = raw
    except Exception as exc:  # noqa: BLE001
        raise OidcError(f"OIDC state verify failed: {exc}", status_code=503) from exc
    if not ok:
        raise OidcError("Invalid or expired OIDC state", status_code=400)


def build_authorize_url(settings: Settings, *, state: str) -> str:
    if not oidc_configured(settings):
        raise OidcError("OIDC is not enabled", status_code=404)
    disc = _discovery(settings)
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes or "openid email profile",
        "state": state,
    }
    return f"{disc['authorization_endpoint']}?{urlencode(params)}"


def exchange_code(settings: Settings, *, code: str) -> dict[str, Any]:
    if not oidc_configured(settings):
        raise OidcError("OIDC is not enabled", status_code=404)
    disc = _discovery(settings)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
    }
    if settings.oidc_client_secret:
        data["client_secret"] = settings.oidc_client_secret
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(disc["token_endpoint"], data=data)
            if resp.status_code >= 400:
                raise OidcError(
                    f"OIDC token exchange failed ({resp.status_code})",
                    status_code=401,
                )
            tokens = resp.json()
    except OidcError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OidcError(f"OIDC token exchange error: {exc}", status_code=502) from exc

    email = None
    name = None
    access = tokens.get("access_token")
    userinfo_url = disc.get("userinfo_endpoint")
    if access and userinfo_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                ui = client.get(
                    userinfo_url, headers={"Authorization": f"Bearer {access}"}
                )
                if ui.status_code < 400:
                    info = ui.json()
                    email = (info.get("email") or "").strip().lower() or None
                    name = (info.get("name") or info.get("preferred_username") or "").strip()
        except Exception:  # noqa: BLE001
            logger.warning("oidc_userinfo_failed", exc_info=True)

    if not email:
        raise OidcError("OIDC did not return an email claim", status_code=401)
    return {"email": email, "display_name": name or email.split("@")[0]}


def login_or_register(db: Session, *, email: str, display_name: str) -> User:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None:
        # Random unusable local password — password login cannot guess SSO accounts
        user = User(
            email=email.lower(),
            password_hash=hash_password(secrets.token_urlsafe(32)),
            display_name=(display_name or email.split("@")[0])[:120],
        )
        db.add(user)
        db.flush()
        workspace_service.create_default_workspace(db, user=user)
        db.commit()
        db.refresh(user)
    return user


def issue_auth_tokens(user: User) -> tuple[str, str]:
    return create_token_pair(user_id=user.id, email=user.email)
