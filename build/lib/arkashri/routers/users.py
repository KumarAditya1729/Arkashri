# pyre-ignore-all-errors
"""
routers/users.py — User Management API

Endpoints:
  POST   /auth/register              Public self-registration
  POST   /auth/users                  Create a new user (ADMIN only)
  GET    /auth/users                  List all users in tenant
  GET    /auth/users/{user_id}        Get single user
  PATCH  /auth/users/{user_id}        Update role / name / active status
  DELETE /auth/users/{user_id}        Soft-delete (deactivate) user
  POST   /auth/users/{user_id}/reset-password  Change password (self or ADMIN)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import User, UserRole, ClientRole
from arkashri.services.auth_sessions import create_login_session
from arkashri.services.password import hash_password, verify_password
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()


# ─── POST /auth/register — Public Self-Registration ──────────────────────────

# Roles that self-registered users are ALLOWED to claim.
# ADMIN and OPERATOR must be assigned by an existing ADMIN via POST /auth/users.
_SELF_REGISTRATION_ALLOWED_ROLES: set[str] = {
    "operator", "reviewer", "read_only", "auditor", "ca",
    "OPERATOR", "REVIEWER", "READ_ONLY",
}


class RegisterRequest(BaseModel):
    email:        EmailStr = Field(..., description="Valid email address")
    password:     str      = Field(..., min_length=8)
    full_name:    str      = Field(..., min_length=1, max_length=255)
    organisation: str | None = None
    role:         str      = "OPERATOR"   # default: full audit operator





@router.post(
    "/register",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
    summary="Public self-registration — creates a new platform user and returns a JWT",
)
async def register_user(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    from fastapi.responses import JSONResponse

    email = payload.email.strip().lower()
    tenant_id = "default_tenant"   # all self-registered users land in default tenant

    # ── SECURITY GATE: Block privilege escalation via self-registration ────────
    # ADMIN can only be assigned by an existing ADMIN via POST /auth/users.
    # Any attempt to self-assign ADMIN is rejected with 403.
    if payload.role.upper() in {"ADMIN", "PARTNER"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "The role 'ADMIN' cannot be self-assigned during registration. "
                "Contact your platform administrator to be granted elevated privileges."
            ),
        )

    if payload.role not in _SELF_REGISTRATION_ALLOWED_ROLES:
        # Unknown role — safe default
        payload.role = "REVIEWER"

    # Check uniqueness
    existing = (await db.scalars(select(User).where(User.email == email))).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Email {payload.email} is already registered.")

    # Map incoming role string to UserRole — ADMIN excluded from map intentionally.
    role_map: dict[str, UserRole] = {
        "operator": UserRole.OPERATOR,
        "OPERATOR": UserRole.OPERATOR,
        "auditor":  UserRole.OPERATOR,
        "ca":       UserRole.OPERATOR,
        "reviewer": UserRole.REVIEWER,
        "REVIEWER": UserRole.REVIEWER,
        "read_only": UserRole.READ_ONLY,
        "READ_ONLY": UserRole.READ_ONLY,
    }
    db_role = role_map.get(payload.role, UserRole.REVIEWER)

    initials = "".join(w[0] for w in payload.full_name.split() if w).upper()[:10] or "AU"

    user = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        initials=initials,
        role=db_role,
        is_active=True,
        created_by="self-registration",
    )
    db.add(user)
    await db.flush()
    bundle = await create_login_session(db, user=user, request=request)
    await db.commit()

    return JSONResponse(
        status_code=201,
        content={
            "access_token": bundle.access_token,
            "refresh_token": bundle.refresh_token,
            "token_type": "bearer",
            "expires_in": bundle.expires_in,
            "user": {
                "id": str(user.id), "email": user.email, "full_name": user.full_name,
                "role": user.role.value, "tenant_id": user.tenant_id, "initials": user.initials,
            },
        },
    )



class CreateUserRequest(BaseModel):
    email:     str = Field(..., min_length=3)
    password:  str = Field(..., min_length=8, description="Min 8 chars")
    full_name: str = Field(..., min_length=1, max_length=255)
    initials:  str = Field(..., min_length=1, max_length=10)
    role:      UserRole = UserRole.REVIEWER


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    initials:  str | None = None
    role:      UserRole | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    current_password: str | None = Field(None, description="Required for self-service reset")
    new_password:     str        = Field(..., min_length=8)


class UserOut(BaseModel):
    id:            str
    tenant_id:     str
    email:         str
    full_name:     str
    initials:      str
    role:          str
    is_active:     bool
    last_login_at: str | None
    created_at:    str

    model_config = {"from_attributes": True}


# ─── POST /auth/users — Create User ──────────────────────────────────────────

@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new platform user (ADMIN only)",
)
async def create_user(
    payload: CreateUserRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> UserOut:
    tenant_id = auth.tenant_id

    # Check email uniqueness within tenant
    existing = (await db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.email == payload.email.lower())
    )).first()
    if existing:
        raise HTTPException(409, f"User with email {payload.email} already exists in this tenant.")

    user = User(
        tenant_id=tenant_id,
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        initials=payload.initials.upper(),
        role=payload.role,
        is_active=True,
        created_by=auth.client_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


# ─── GET /auth/users — List Users ────────────────────────────────────────────

@router.get(
    "/users",
    response_model=list[UserOut],
    summary="List all users in the tenant",
)
async def list_users(
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> list[UserOut]:
    users = (await db.scalars(
        select(User)
        .where(User.tenant_id == auth.tenant_id)
        .order_by(User.email)
    )).all()
    return [_user_out(u) for u in users]


# ─── GET /auth/users/{user_id} — Get User ────────────────────────────────────

@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Get a single user by ID",
)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> UserOut:
    user = await _get_or_404(db, user_id, auth.tenant_id)
    return _user_out(user)


# ─── PATCH /auth/users/{user_id} — Update User ───────────────────────────────

@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Update user role, name, or active status (ADMIN only)",
)
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> UserOut:
    user = await _get_or_404(db, user_id, auth.tenant_id)

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.initials is not None:
        user.initials = payload.initials.upper()
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


# ─── DELETE /auth/users/{user_id} — Soft Delete ──────────────────────────────

@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate (soft-delete) a user",
)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> None:
    user = await _get_or_404(db, user_id, auth.tenant_id)
    if not user.is_active:
        raise HTTPException(409, "User is already deactivated.")
    user.is_active = False
    db.add(user)
    await db.commit()


# ─── POST /auth/users/{user_id}/reset-password ───────────────────────────────

@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset a user's password (self-service requires current_password; ADMIN can skip it)",
)
async def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    user = await _get_or_404(db, user_id, auth.tenant_id)

    # Determine caller identity — compare string forms of both IDs
    is_self = str(user.id) == str(getattr(auth, "client_id", ""))
    is_admin = getattr(auth, "role", None) == ClientRole.ADMIN

    # Non-admins can only reset their own password, and must supply current_password
    if not is_admin:
        if not is_self:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only reset your own password. Contact an ADMIN to reset another user's password.",
            )
        if not payload.current_password:
            raise HTTPException(422, "current_password is required for self-service password reset.")
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(401, "current_password is incorrect.")

    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    await db.commit()
    return {"message": "Password updated successfully."}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_404(db: AsyncSession, user_id: uuid.UUID, tenant_id: str) -> User:
    user = (await db.scalars(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )).first()
    if not user:
        raise HTTPException(404, "User not found.")
    return user


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        tenant_id=u.tenant_id,
        email=u.email,
        full_name=u.full_name,
        initials=u.initials,
        role=u.role.value,
        is_active=u.is_active,
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
        created_at=u.created_at.isoformat(),
    )
