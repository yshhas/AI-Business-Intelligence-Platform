from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import (
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenRefreshResponse,
    UserOut,
    WorkspaceOut,
)
from app.services import rate_limit
from app.services import refresh_sessions as rs
from app.services import workspace_service
from app.services.rate_limit import RateLimitExceeded

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_key(request: Request, email: str | None = None) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    suffix = (email or "").strip().lower() or "-"
    return f"{ip}:{suffix}"


def _auth_response(
    db: Session,
    user: User,
    workspace_out: WorkspaceOut | None,
) -> AuthResponse:
    access, refresh = rs.issue_token_pair(db, user_id=user.id, email=user.email)
    db.commit()
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
        workspace=workspace_out,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    try:
        rate_limit.check_auth_rate_limit(client_key=_client_key(request, body.email))
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    existing = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(user)
    db.flush()

    workspace, member = workspace_service.create_default_workspace(db, user=user)
    db.commit()
    db.refresh(user)
    db.refresh(workspace)

    return _auth_response(
        db,
        user,
        WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            role=member.role,
            created_at=workspace.created_at,
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    try:
        rate_limit.check_auth_rate_limit(client_key=_client_key(request, body.email))
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    memberships = workspace_service.list_memberships_for_user(db, user_id=user.id)
    workspace_out = None
    if memberships:
        workspace, role = memberships[0]
        workspace_out = WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            role=role,
            created_at=workspace.created_at,
        )

    return _auth_response(db, user, workspace_out)


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenRefreshResponse:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_id = UUID(str(payload["sub"]))
        jti = str(payload.get("jti") or "")
        if not jti:
            raise InvalidTokenError("missing jti")
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        access, new_refresh = rs.rotate_refresh(
            db, user_id=user.id, email=user.email, old_jti=jti
        )
        db.commit()
    except rs.RefreshSessionError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return TokenRefreshResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, db: Session = Depends(get_db)) -> None:
    """Revoke the current refresh session (this device). Best-effort for clients."""
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        jti = str(payload.get("jti") or "")
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        # Idempotent: bad token → still 204 (client clears local storage)
        return None
    if jti:
        rs.revoke_jti(db, jti=jti)
        db.commit()
    return None


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/oidc/login")
def oidc_login() -> dict:
    """Return IdP authorize URL when OIDC is configured; else 404."""
    from uuid import uuid4

    from app.core.config import get_settings
    from app.services import oidc_service

    settings = get_settings()
    if not oidc_service.oidc_configured(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC not enabled")
    try:
        state = uuid4().hex
        oidc_service.store_oauth_state(state)
        url = oidc_service.build_authorize_url(settings, state=state)
    except oidc_service.OidcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"authorize_url": url, "state": state}


@router.post("/oidc/callback", response_model=AuthResponse)
def oidc_callback(
    body: dict,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Exchange authorization code for local JWT pair (MVP)."""
    from app.core.config import get_settings
    from app.services import oidc_service

    settings = get_settings()
    if not oidc_service.oidc_configured(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC not enabled")
    code = str((body or {}).get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code required")
    try:
        oidc_service.consume_oauth_state((body or {}).get("state"))
        profile = oidc_service.exchange_code(settings, code=code)
        user = oidc_service.login_or_register(
            db, email=profile["email"], display_name=profile.get("display_name") or ""
        )
    except oidc_service.OidcError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    memberships = workspace_service.list_memberships_for_user(db, user_id=user.id)
    workspace_out = None
    if memberships:
        workspace, role = memberships[0]
        workspace_out = WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            role=role,
            created_at=workspace.created_at,
        )
    return _auth_response(db, user, workspace_out)
