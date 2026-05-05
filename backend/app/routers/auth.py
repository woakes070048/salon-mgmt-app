import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.deps import CurrentUser
from app.email import email_cfg_from_row, send_password_reset_email
from app.models.client import Client
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

    if user is None or not verify_password(body.password, user.password_hash):
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


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role.value,
        tenant_id=str(current_user.tenant_id),
        language_preference=current_user.language_preference or "en",
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
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role.value,
        tenant_id=str(current_user.tenant_id),
        language_preference=current_user.language_preference,
    )
