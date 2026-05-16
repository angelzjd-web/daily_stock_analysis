# -*- coding: utf-8 -*-
"""Authentication endpoints — multi-user registration, login, and admin user management."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_HOURS_DEFAULT,
    admin_reset_user_password,
    authenticate_user,
    change_user_password,
    check_rate_limit,
    clear_rate_limit,
    create_session,
    create_user,
    delete_user,
    ensure_admin_user,
    get_client_ip,
    get_session_user_id,
    get_session_user_role,
    get_user_by_id,
    get_user_by_username,
    has_stored_password,
    is_auth_enabled,
    is_password_changeable,
    is_password_set,
    list_users,
    record_login_failure,
    refresh_auth_state,
    rotate_session_secret,
    set_initial_password,
    update_user,
    verify_password,
    verify_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Login request body."""
    model_config = {"populate_by_name": True}
    username: str = Field(default="admin", description="Username")
    password: str = Field(default="", description="Password")
    # Legacy: first-time setup support
    password_confirm: str | None = Field(default=None, alias="passwordConfirm", description="Confirm (first-time)")


class RegisterRequest(BaseModel):
    """Register a new user."""
    model_config = {"populate_by_name": True}
    username: str = Field(min_length=3, max_length=64, description="Username")
    password: str = Field(min_length=6, description="Password")
    password_confirm: str = Field(alias="passwordConfirm", description="Confirm password")
    email: str | None = Field(default=None, description="Email (optional)")


class ChangePasswordRequest(BaseModel):
    """Change password request body."""
    model_config = {"populate_by_name": True}
    current_password: str = Field(default="", alias="currentPassword")
    new_password: str = Field(default="", alias="newPassword")
    new_password_confirm: str = Field(default="", alias="newPasswordConfirm")


class AdminCreateUserRequest(BaseModel):
    """Admin creates a new user."""
    model_config = {"populate_by_name": True}
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    password_confirm: str = Field(alias="passwordConfirm")
    role: str = Field(default="user", description="admin or user")
    email: str | None = Field(default=None)


class AdminUpdateUserRequest(BaseModel):
    """Admin updates a user."""
    model_config = {"populate_by_name": True}
    role: str | None = Field(default=None)
    email: str | None = Field(default=None)
    is_active: bool | None = Field(default=None, alias="isActive")
    password: str | None = Field(default=None)
    password_confirm: str | None = Field(default=None, alias="passwordConfirm")
    points_balance: int | None = Field(default=None, alias="pointsBalance")


class AdminResetPasswordRequest(BaseModel):
    """Admin resets a user's password."""
    model_config = {"populate_by_name": True}
    new_password: str = Field(min_length=6, alias="newPassword")
    new_password_confirm: str = Field(alias="newPasswordConfirm")


class AuthSettingsRequest(BaseModel):
    """Update auth enablement and initial password settings."""
    model_config = {"populate_by_name": True}
    auth_enabled: bool = Field(alias="authEnabled")
    password: str = Field(default="")
    password_confirm: str | None = Field(default=None, alias="passwordConfirm")
    current_password: str = Field(default="", alias="currentPassword")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _cookie_params(request: Request) -> dict:
    """Build cookie params including Secure based on request."""
    secure = False
    if os.getenv("TRUST_X_FORWARDED_FOR", "false").lower() == "true":
        proto = request.headers.get("X-Forwarded-Proto", "").lower()
        secure = proto == "https"
    else:
        secure = request.url.scheme == "https"

    try:
        max_age_hours = int(os.getenv("ADMIN_SESSION_MAX_AGE_HOURS", str(SESSION_MAX_AGE_HOURS_DEFAULT)))
    except ValueError:
        max_age_hours = SESSION_MAX_AGE_HOURS_DEFAULT
    max_age = max_age_hours * 3600

    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
        "max_age": max_age,
    }


def _set_session_cookie(response: Response, session_value: str, request: Request) -> None:
    """Attach the session cookie to a response."""
    params = _cookie_params(request)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_value,
        httponly=params["httponly"],
        samesite=params["samesite"],
        secure=params["secure"],
        path=params["path"],
        max_age=params["max_age"],
    )


def _get_current_user(request: Request) -> dict | None:
    """Get current user info from request state."""
    user_id = getattr(request.state, "user_id", None)
    user_role = getattr(request.state, "user_role", None)
    if not user_id:
        return None
    return {"id": user_id, "role": user_role}


def _require_admin(request: Request) -> JSONResponse | None:
    """Return error response if not admin, or None if admin."""
    current = _get_current_user(request)
    if not current or current["role"] != "admin":
        return JSONResponse(
            status_code=403,
            content={"error": "forbidden", "message": "需要管理员权限"},
        )
    return None


# ------------------------------------------------------------------
# Auth status
# ------------------------------------------------------------------

def _get_auth_status_dict(request: Request | None = None) -> dict:
    """Build consistent auth status response body."""
    auth_enabled = is_auth_enabled()
    logged_in = False
    current_user = None

    if auth_enabled and request:
        cookie_val = request.cookies.get(COOKIE_NAME)
        if cookie_val:
            session_data = verify_session(cookie_val)
            if session_data:
                logged_in = True
                user = get_user_by_id(session_data["user_id"])
                if user:
                    current_user = {
                        "id": user["id"],
                        "username": user["username"],
                        "role": user["role"],
                        "email": user["email"],
                        "pointsBalance": user.get("points_balance", 0),
                    }

    if auth_enabled:
        setup_state = "enabled"
    elif has_stored_password():
        setup_state = "password_retained"
    else:
        setup_state = "no_password"

    result = {
        "authEnabled": auth_enabled,
        "loggedIn": logged_in,
        "passwordSet": is_password_set() if auth_enabled else False,
        "passwordChangeable": is_password_changeable() if auth_enabled else False,
        "setupState": setup_state,
    }

    if current_user:
        result["currentUser"] = current_user

    return result


@router.get(
    "/status",
    summary="Get auth status",
    description="Returns whether auth is enabled and if the current request is logged in.",
)
async def auth_status(request: Request):
    """Return authEnabled, loggedIn, currentUser, etc."""
    return _get_auth_status_dict(request)


# ------------------------------------------------------------------
# Auth settings (legacy compat for AuthSettingsCard)
# ------------------------------------------------------------------

@router.post(
    "/settings",
    summary="Update auth settings",
    description="Enable or disable password login. Admin only.",
)
async def auth_update_settings(request: Request, body: AuthSettingsRequest):
    """Manage auth enablement from the settings page. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    target_enabled = body.auth_enabled
    current_enabled = is_auth_enabled()

    # If re-enabling and no password set, require password
    if target_enabled and body.password:
        password = (body.password or "").strip()
        confirm = (body.password_confirm or "").strip()
        if password != confirm:
            return JSONResponse(
                status_code=400,
                content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
            )
        # Create admin user if not exists
        if not is_password_set():
            err = set_initial_password(password)
            if err:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_password", "message": err},
                )

    # Toggle auth enabled in .env
    if target_enabled != current_enabled:
        from src.config import Config, setup_env
        from src.core.config_manager import ConfigManager
        from api.deps import get_system_config_service

        manager_applied = False
        try:
            service = get_system_config_service(request)
            service.apply_simple_updates(
                updates=[("ADMIN_AUTH_ENABLED", "true" if target_enabled else "false")],
                mask_token="******",
            )
            manager_applied = True
        except Exception:
            manager_applied = False

        if not manager_applied:
            try:
                manager = ConfigManager()
                manager.apply_updates(
                    updates=[("ADMIN_AUTH_ENABLED", "true" if target_enabled else "false")],
                    sensitive_keys=set(),
                    mask_token="******",
                )
                manager_applied = True
            except Exception:
                pass

        if manager_applied:
            Config.reset_instance()
            setup_env(override=True)
            refresh_auth_state()
            rotate_session_secret()

    # Re-create session after settings change
    current = _get_current_user(request)
    if current and target_enabled:
        session_val = create_session(current["id"], current["role"])
        content = _get_auth_status_dict(request)
        content["loggedIn"] = True
        resp = JSONResponse(content=content)
        if session_val:
            _set_session_cookie(resp, session_val, request)
        return resp

    resp = JSONResponse(content=_get_auth_status_dict(request))
    if not target_enabled:
        resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

@router.post(
    "/login",
    summary="Login with username and password",
    description="Authenticate and set session cookie.",
)
async def auth_login(request: Request, body: LoginRequest):
    """Verify username/password and set cookie on success."""
    if not is_auth_enabled():
        return JSONResponse(
            status_code=400,
            content={"error": "auth_disabled", "message": "认证功能未启用"},
        )

    username = (body.username or "").strip()
    password = (body.password or "").strip()

    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"error": "fields_required", "message": "请输入用户名和密码"},
        )

    ip = get_client_ip(request)
    if not check_rate_limit(ip):
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "message": "尝试次数过多，请稍后再试"},
        )

    # First-time setup: if no admin user exists and username is "admin"
    if username == "admin" and not is_password_set():
        confirm = (body.password_confirm or "").strip()
        if password != confirm:
            record_login_failure(ip)
            return JSONResponse(
                status_code=400,
                content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
            )
        err = set_initial_password(password)
        if err:
            record_login_failure(ip)
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_password", "message": err},
            )

    user = authenticate_user(username, password)
    if user is None:
        record_login_failure(ip)
        return JSONResponse(
            status_code=401,
            content={"error": "invalid_credentials", "message": "用户名或密码错误"},
        )

    clear_rate_limit(ip)
    session_val = create_session(user["id"], user["role"])
    if not session_val:
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "创建会话失败"},
        )

    resp_data = {
        "ok": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
    }
    resp = JSONResponse(content=resp_data)
    _set_session_cookie(resp, session_val, request)
    return resp


# ------------------------------------------------------------------
# Register (open registration or admin-only)
# ------------------------------------------------------------------

@router.post(
    "/register",
    summary="Register a new user",
    description="Register a new user account. If no admin exists, the first user becomes admin.",
)
async def auth_register(request: Request, body: RegisterRequest):
    """Register a new user."""
    if not is_auth_enabled():
        return JSONResponse(
            status_code=400,
            content={"error": "auth_disabled", "message": "认证功能未启用"},
        )

    username = body.username.strip()
    password = body.password.strip()
    confirm = body.password_confirm.strip()

    if password != confirm:
        return JSONResponse(
            status_code=400,
            content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
        )

    # Determine role: first user becomes admin
    from src.auth import get_user_by_username
    any_user = get_user_by_username(username)
    if any_user:
        return JSONResponse(
            status_code=400,
            content={"error": "username_exists", "message": "用户名已存在"},
        )

    # Check if any admin exists; if not, first registered user becomes admin
    all_users = list_users()
    has_admin = any(u["role"] == "admin" for u in all_users)
    role = "admin" if not has_admin else "user"

    # Open registration: anyone can register as "user"
    if has_admin:
        role = "user"

    user_id, err = create_user(username, password, role=role, email=body.email)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "registration_failed", "message": err},
        )

    # Auto-login after registration if no existing session
    current = _get_current_user(request)
    if not current:
        session_val = create_session(user_id, role)
        resp = JSONResponse(content={
            "ok": True,
            "user": {"id": user_id, "username": username, "role": role},
        })
        if session_val:
            _set_session_cookie(resp, session_val, request)
        return resp

    return JSONResponse(content={
        "ok": True,
        "user": {"id": user_id, "username": username, "role": role},
    })


# ------------------------------------------------------------------
# Change password (own account)
# ------------------------------------------------------------------

@router.post(
    "/change-password",
    summary="Change own password",
    description="Change password. Requires valid session.",
)
async def auth_change_password(request: Request, body: ChangePasswordRequest):
    """Change password. Requires login."""
    current = _get_current_user(request)
    if not current:
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "请先登录"},
        )

    current_pwd = (body.current_password or "").strip()
    new_pwd = (body.new_password or "").strip()
    new_confirm = (body.new_password_confirm or "").strip()

    if not current_pwd:
        return JSONResponse(
            status_code=400,
            content={"error": "current_required", "message": "请输入当前密码"},
        )
    if new_pwd != new_confirm:
        return JSONResponse(
            status_code=400,
            content={"error": "password_mismatch", "message": "两次输入的新密码不一致"},
        )

    err = change_user_password(current["id"], current_pwd, new_pwd)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_password", "message": err},
        )
    return Response(status_code=204)


# ------------------------------------------------------------------
# Logout
# ------------------------------------------------------------------

@router.post(
    "/logout",
    summary="Logout",
    description="Clear session cookie.",
)
async def auth_logout(request: Request):
    """Clear session cookie."""
    if is_auth_enabled() and not rotate_session_secret():
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "Failed to invalidate session"},
        )
    resp = Response(status_code=204)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


# ------------------------------------------------------------------
# Admin user management endpoints
# ------------------------------------------------------------------

@router.get(
    "/users",
    summary="List all users (admin only)",
    description="Admin endpoint to list all registered users.",
)
async def admin_list_users(request: Request):
    """List all users. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp
    users = list_users()
    return JSONResponse(content={"users": users})


@router.post(
    "/users",
    summary="Create a new user (admin only)",
    description="Admin endpoint to create a new user with specified role.",
)
async def admin_create_user(request: Request, body: AdminCreateUserRequest):
    """Create a new user. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    password = body.password.strip()
    confirm = body.password_confirm.strip()

    if password != confirm:
        return JSONResponse(
            status_code=400,
            content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
        )

    role = body.role.strip() if body.role else "user"
    user_id, err = create_user(
        username=body.username.strip(),
        password=password,
        role=role,
        email=body.email,
    )
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "create_failed", "message": err},
        )

    return JSONResponse(content={
        "ok": True,
        "user": {"id": user_id, "username": body.username.strip(), "role": role},
    })


@router.put(
    "/users/{user_id}",
    summary="Update a user (admin only)",
    description="Admin endpoint to update user role, status, or reset password.",
)
async def admin_update_user(request: Request, user_id: int, body: AdminUpdateUserRequest):
    """Update a user. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    updates = {}
    if body.role is not None:
        updates["role"] = body.role
    if body.email is not None:
        updates["email"] = body.email
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.points_balance is not None:
        updates["points_balance"] = body.points_balance

    # Password reset
    if body.password is not None:
        confirm = body.password_confirm or ""
        if body.password != confirm:
            return JSONResponse(
                status_code=400,
                content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
            )
        updates["password"] = body.password

    if not updates:
        return JSONResponse(
            status_code=400,
            content={"error": "no_updates", "message": "没有需要更新的字段"},
        )

    err = update_user(user_id, **updates)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "update_failed", "message": err},
        )

    return JSONResponse(content={"ok": True})


@router.delete(
    "/users/{user_id}",
    summary="Delete a user (admin only)",
    description="Admin endpoint to delete a user.",
)
async def admin_delete_user(request: Request, user_id: int):
    """Delete a user. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    # Don't allow deleting yourself
    current = _get_current_user(request)
    if current and current["id"] == user_id:
        return JSONResponse(
            status_code=400,
            content={"error": "self_delete", "message": "不能删除自己的账户"},
        )

    err = delete_user(user_id)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "delete_failed", "message": err},
        )

    return JSONResponse(content={"ok": True})


@router.post(
    "/users/{user_id}/reset-password",
    summary="Reset user password (admin only)",
    description="Admin endpoint to reset a user's password.",
)
async def admin_reset_password(request: Request, user_id: int, body: AdminResetPasswordRequest):
    """Reset a user's password. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    if body.new_password != body.new_password_confirm:
        return JSONResponse(
            status_code=400,
            content={"error": "password_mismatch", "message": "两次输入的密码不一致"},
        )

    current = _get_current_user(request)
    if not current:
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "请先登录"},
        )

    err = admin_reset_user_password(current["id"], user_id, body.new_password)
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "reset_failed", "message": err},
        )

    return JSONResponse(content={"ok": True})


class AdminSetPointsRequest(BaseModel):
    """Admin sets user points."""
    model_config = {"populate_by_name": True}
    balance: int = Field(description="New points balance")
    reason: str | None = Field(default=None, description="Reason for change")


@router.post(
    "/users/{user_id}/points",
    summary="Set user points (admin only)",
    description="Admin endpoint to set a user's points balance.",
)
async def admin_set_points_endpoint(request: Request, user_id: int, body: AdminSetPointsRequest):
    """Set a user's points balance. Admin only."""
    err_resp = _require_admin(request)
    if err_resp:
        return err_resp

    from src.points import admin_set_points as _set_points
    err = _set_points(user_id, body.balance, body.reason or "")
    if err:
        return JSONResponse(
            status_code=400,
            content={"error": "set_points_failed", "message": err},
        )

    return JSONResponse(content={"ok": True, "balance": body.balance})
