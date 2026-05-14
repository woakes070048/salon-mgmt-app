import hashlib
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.deps import CurrentUser
from app.email import email_cfg_from_row, send_password_reset_email
from app.models.client import Client
from app.models.provider import Provider
from app.models.email_config import TenantEmailConfig
from app.models.tenant import Tenant
from app.models.user import LoginLog, PasswordResetToken, User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    language_preference: str
    display_name: str | None = None
    provider_id: str | None = None   # set if this user is a provider

    model_config = {"from_attributes": True}


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(
        select(User).where(User.email == body.email, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    if user is None or user.password_hash is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    db.add(LoginLog(tenant_id=user.tenant_id, user_id=user.id, email=user.email))
    await db.commit()

    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        tenant_id=str(user.tenant_id),
    )
    return TokenResponse(access_token=token)


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    password: str
    language_preference: str = "en"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    tenant = (
        await db.execute(
            select(Tenant).where(
                Tenant.slug == settings.default_tenant_slug,
                Tenant.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Registration unavailable")

    existing = (
        await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == body.email)
        )
    ).scalar_one_or_none()

    if existing is not None and existing.is_active:
        # Block only if there is also an active client linked to this user
        active_client = (
            await db.execute(
                select(Client).where(
                    Client.user_id == existing.id,
                    Client.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if active_client is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        # Active user but client was deleted — deactivate to allow re-registration
        existing.is_active = False

    if existing is not None:
        # Reactivate the previously deactivated account with fresh credentials
        existing.is_active = True
        existing.password_hash = hash_password(body.password)
        user = existing
    else:
        user = User(
            tenant_id=tenant.id,
            email=body.email,
            password_hash=hash_password(body.password),
            role=UserRole.guest,
            language_preference=body.language_preference,
        )
        db.add(user)
    await db.flush()

    client_code = f"G{random.randint(10000, 99999)}"
    client = Client(
        tenant_id=tenant.id,
        user_id=user.id,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        cell_phone=body.phone,
        client_code=client_code,
        language_preference=body.language_preference,
    )
    db.add(client)
    await db.commit()

    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        tenant_id=str(user.tenant_id),
    )
    return TokenResponse(access_token=token)


class RequestResetRequest(BaseModel):
    email: EmailStr


@router.post("/request-reset", status_code=status.HTTP_204_NO_CONTENT)
async def request_reset(
    body: RequestResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = (
        await db.execute(
            select(User).where(User.email == body.email, User.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if user is None:
        return

    email_cfg_row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == user.tenant_id)
        )
    ).scalar_one_or_none()
    if email_cfg_row is None:
        return

    raw = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
    ))
    await db.commit()

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    ).scalar_one()
    reset_link = f"{settings.frontend_url}/reset-password?token={raw}"
    await send_password_reset_email(email_cfg_from_row(email_cfg_row), tenant, user.email, reset_link)


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    reset_token = (
        await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
        )
    ).scalar_one_or_none()
    if reset_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user = (
        await db.execute(select(User).where(User.id == reset_token.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user.password_hash = hash_password(body.password)
    user.is_active = True
    reset_token.used_at = datetime.now(timezone.utc)
    await db.commit()


def _display_name(user: User) -> str | None:
    parts = [user.first_name, user.last_name]
    name = " ".join(p for p in parts if p)
    return name or None


async def _provider_id_for_user(user_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> str | None:
    row = (await db.execute(
        select(Provider.id).where(Provider.user_id == user_id, Provider.tenant_id == tenant_id)
    )).scalar_one_or_none()
    return str(row) if row else None


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> MeResponse:
    display = _display_name(current_user)
    # For guests, fall back to their linked client name
    if not display and current_user.role == UserRole.guest:
        linked = (await db.execute(
            select(Client).where(
                Client.user_id == current_user.id,
                Client.tenant_id == current_user.tenant_id,
                Client.is_active == True,  # noqa: E712
            )
        )).scalar_one_or_none()
        if linked:
            display = " ".join(p for p in [linked.first_name, linked.last_name] if p) or None
    provider_id = await _provider_id_for_user(current_user.id, current_user.tenant_id, db)
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role.value,
        tenant_id=str(current_user.tenant_id),
        language_preference=current_user.language_preference or "en",
        display_name=display,
        provider_id=provider_id,
    )


class UpdateMeRequest(BaseModel):
    language_preference: str


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateMeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    from app.i18n import SUPPORTED_LANGUAGES
    if body.language_preference not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported language")
    current_user.language_preference = body.language_preference
    await db.commit()
    await db.refresh(current_user)
    provider_id = await _provider_id_for_user(current_user.id, current_user.tenant_id, db)
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role.value,
        tenant_id=str(current_user.tenant_id),
        language_preference=current_user.language_preference,
        display_name=_display_name(current_user),
        provider_id=provider_id,
    )


@router.get("/oauth/start")
async def oauth_start(provider: str) -> RedirectResponse:
    if not settings.auth0_domain or not settings.auth0_client_id:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="SSO not configured")
    if provider not in ("google",):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")
    connection = "google-oauth2"
    state = secrets.token_urlsafe(16)
    params = urlencode({
        "response_type": "code",
        "client_id": settings.auth0_client_id,
        "redirect_uri": settings.auth0_callback_url,
        "scope": "openid email profile",
        "connection": connection,
        "state": state,
    })
    resp = RedirectResponse(f"https://{settings.auth0_domain}/authorize?{params}")
    resp.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=300)
    return resp


@router.get("/callback")
async def oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        return RedirectResponse(f"{settings.frontend_url}/login?error=state_mismatch")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"https://{settings.auth0_domain}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": settings.auth0_client_id,
                "client_secret": settings.auth0_client_secret,
                "code": code,
                "redirect_uri": settings.auth0_callback_url,
            },
        )
    if token_resp.status_code != 200:
        return RedirectResponse(f"{settings.frontend_url}/login?error=token_exchange")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            f"https://{settings.auth0_domain}/userinfo",
            headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
        )
    if userinfo_resp.status_code != 200:
        return RedirectResponse(f"{settings.frontend_url}/login?error=userinfo")

    info = userinfo_resp.json()
    auth0_sub: str = info["sub"]
    email: str | None = info.get("email")
    name_parts = (info.get("name") or "").split(maxsplit=1)
    given_name: str | None = info.get("given_name") or (name_parts[0] if name_parts else None)
    family_name: str | None = info.get("family_name") or (name_parts[1] if len(name_parts) > 1 else None)

    tenant = (await db.execute(
        select(Tenant).where(Tenant.slug == settings.default_tenant_slug, Tenant.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if tenant is None:
        return RedirectResponse(f"{settings.frontend_url}/login?error=no_tenant")

    user = (await db.execute(
        select(User).where(User.auth0_sub == auth0_sub, User.tenant_id == tenant.id)
    )).scalar_one_or_none()

    if user is None and email:
        user = (await db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant.id, User.is_active == True)  # noqa: E712
        )).scalar_one_or_none()
        if user:
            user.auth0_sub = auth0_sub

    if user is None:
        if not email:
            return RedirectResponse(f"{settings.frontend_url}/login?error=no_email")
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=None,
            role=UserRole.guest,
            auth0_sub=auth0_sub,
            first_name=given_name,
            last_name=family_name,
        )
        db.add(user)
        await db.flush()
        client_obj = Client(
            tenant_id=tenant.id,
            user_id=user.id,
            first_name=given_name or "",
            last_name=family_name or "",
            email=email,
            client_code=f"G{random.randint(10000, 99999)}",
        )
        db.add(client_obj)

    db.add(LoginLog(tenant_id=user.tenant_id, user_id=user.id, email=user.email))
    await db.commit()

    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        tenant_id=str(user.tenant_id),
    )
    resp = RedirectResponse(f"{settings.frontend_url}/oauth-callback?token={token}")
    resp.delete_cookie("oauth_state")
    return resp


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    if current_user.password_hash is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO accounts do not have a password")
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
