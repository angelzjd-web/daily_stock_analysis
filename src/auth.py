# -*- coding: utf-8 -*-
"""
Web authentication module — multi-user support.

Features:
- User registration (admin or normal user)
- Login with username + password
- Cookie-based sessions with HMAC signing (includes user_id + role)
- Role-based access control (admin / user)
- Rate limiting per IP
- CLI password reset for admin
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

COOKIE_NAME = "dsa_session"
PBKDF2_ITERATIONS = 100_000
RATE_LIMIT_WINDOW_SEC = 300
RATE_LIMIT_MAX_FAILURES = 5
SESSION_MAX_AGE_HOURS_DEFAULT = 24
MIN_PASSWORD_LEN = 6
MIN_USERNAME_LEN = 3

# Lazy-loaded state
_auth_enabled: Optional[bool] = None
_session_secret: Optional[bytes] = None
_rate_limit: dict[str, Tuple[int, float]] = {}
_rate_limit_lock = None


def _get_lock():
    """Lazy init threading lock for rate limit dict."""
    global _rate_limit_lock
    if _rate_limit_lock is None:
        import threading
        _rate_limit_lock = threading.Lock()
    return _rate_limit_lock


def _ensure_env_loaded() -> None:
    """Ensure .env is loaded before reading config."""
    from src.config import setup_env
    setup_env()


def _get_data_dir() -> Path:
    """Return DATA_DIR as parent of DATABASE_PATH."""
    db_path = os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    return Path(db_path).resolve().parent


def _is_auth_enabled_from_env() -> bool:
    """Read ADMIN_AUTH_ENABLED from .env file."""
    _ensure_env_loaded()
    env_file = os.getenv("ENV_FILE")
    env_path = Path(env_file) if env_file else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return False
    values = dotenv_values(env_path)
    val = (values.get("ADMIN_AUTH_ENABLED") or "").strip().lower()
    return val in ("true", "1", "yes")


def rotate_session_secret() -> bool:
    """Rotate the session signing secret to invalidate all active sessions."""
    global _session_secret
    data_dir = _get_data_dir()
    secret_path = data_dir / ".session_secret"
    data_dir.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_bytes(32)
    try:
        tmp_path = secret_path.with_suffix(".tmp")
        tmp_path.write_bytes(new_secret)
        tmp_path.chmod(0o600)
        tmp_path.replace(secret_path)
        _session_secret = new_secret
        logger.info("Session secret rotated successfully")
        return True
    except OSError as e:
        logger.error("Failed to rotate .session_secret: %s", e)
        return False


def _load_session_secret() -> Optional[bytes]:
    """Load or create session secret."""
    global _session_secret
    if _session_secret is not None:
        return _session_secret

    data_dir = _get_data_dir()
    secret_path = data_dir / ".session_secret"

    try:
        if secret_path.exists():
            _session_secret = secret_path.read_bytes()
            if len(_session_secret) != 32:
                logger.warning("Invalid .session_secret length, regenerating")
                _session_secret = None
                if rotate_session_secret():
                    return _session_secret
                return None
            return _session_secret

        data_dir.mkdir(parents=True, exist_ok=True)
        new_secret = secrets.token_bytes(32)
        try:
            with open(secret_path, "xb") as f:
                f.write(new_secret)
            secret_path.chmod(0o600)
        except FileExistsError:
            _session_secret = secret_path.read_bytes()
        else:
            _session_secret = new_secret
        return _session_secret
    except OSError as e:
        logger.error("Failed to create or read .session_secret: %s", e)
        return None


# ------------------------------------------------------------------
# Password hashing utilities
# ------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2. Returns salt_b64:hash_b64."""
    salt = secrets.token_bytes(32)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.standard_b64encode(salt).decode("ascii")
    hash_b64 = base64.standard_b64encode(derived).decode("ascii")
    return f"{salt_b64}:{hash_b64}"


def verify_password_hash(password: str, stored_hash_str: str) -> bool:
    """Verify password against stored salt_b64:hash_b64 string."""
    if not stored_hash_str or ":" not in stored_hash_str:
        return False
    parts = stored_hash_str.strip().split(":", 1)
    if len(parts) != 2:
        return False
    try:
        salt = base64.standard_b64decode(parts[0].strip())
        stored_hash = base64.standard_b64decode(parts[1].strip())
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return hmac.compare_digest(computed, stored_hash)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------
# Legacy file-based admin password support (for migration)
# ------------------------------------------------------------------

def _get_credential_path() -> Path:
    """Path to stored password hash file (legacy)."""
    return _get_data_dir() / ".admin_password_hash"


def _load_credential_from_file() -> bool:
    """Load legacy credential from file. Returns True if loaded."""
    path = _get_credential_path()
    return path.exists()


def has_stored_password() -> bool:
    """Return whether a valid stored password hash exists on disk (legacy)."""
    return _load_credential_from_file()


def verify_stored_password(password: str) -> bool:
    """Verify password against legacy file-based credential."""
    path = _get_credential_path()
    if not path.exists():
        return False
    try:
        raw = path.read_text().strip()
        if not raw or ":" not in raw:
            return False
        parts = raw.strip().split(":", 1)
        if len(parts) != 2:
            return False
        salt = base64.standard_b64decode(parts[0].strip())
        stored_hash = base64.standard_b64decode(parts[1].strip())
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return hmac.compare_digest(computed, stored_hash)
    except (OSError, ValueError, TypeError):
        return False


def _validate_password(pwd: str) -> Optional[str]:
    """Return error message if invalid, None if valid."""
    if not pwd or not pwd.strip():
        return "密码不能为空"
    if len(pwd) < MIN_PASSWORD_LEN:
        return f"密码至少 {MIN_PASSWORD_LEN} 位"
    return None


def _validate_username(username: str) -> Optional[str]:
    """Return error message if invalid, None if valid."""
    if not username or not username.strip():
        return "用户名不能为空"
    if len(username) < MIN_USERNAME_LEN:
        return f"用户名至少 {MIN_USERNAME_LEN} 个字符"
    import re
    if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]+$', username):
        return "用户名只能包含字母、数字、下划线或中文"
    return None


# ------------------------------------------------------------------
# Auth state management
# ------------------------------------------------------------------

def refresh_auth_state() -> None:
    """Reload auth-related state from disk and env."""
    global _auth_enabled, _session_secret
    _auth_enabled = None
    _session_secret = None


def is_auth_enabled() -> bool:
    """Return whether admin authentication is enabled (ADMIN_AUTH_ENABLED=true)."""
    global _auth_enabled
    if _auth_enabled is not None:
        return _auth_enabled
    _auth_enabled = _is_auth_enabled_from_env()
    return _auth_enabled


def is_password_set() -> bool:
    """Return whether at least one user exists in the database."""
    if not is_auth_enabled():
        return False
    try:
        from src.storage import get_db
        db = get_db()
        with db.get_session() as session:
            from src.storage import User
            count = session.query(User).filter(User.is_active == True).count()
            return count > 0
    except Exception:
        return False


def is_password_changeable() -> bool:
    """Return whether password can be changed via web (always True when auth enabled)."""
    return is_auth_enabled()


def _get_session_secret() -> Optional[bytes]:
    """Return session signing secret."""
    if not is_auth_enabled():
        return None
    return _load_session_secret()


# ------------------------------------------------------------------
# Session management (cookie contains user_id + role)
# ------------------------------------------------------------------

def create_session(user_id: int, role: str = "user") -> str:
    """Create a signed session payload. Format: payload.signature where payload = base64(json({nonce, ts, uid, role}))."""
    secret = _get_session_secret()
    if not secret:
        return ""
    nonce = secrets.token_urlsafe(16)
    ts = int(time.time())
    payload_data = {
        "n": nonce,
        "t": ts,
        "u": user_id,
        "r": role,
    }
    payload_json = json.dumps(payload_data, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret, f"{payload_b64}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session(value: str) -> Optional[Dict[str, Any]]:
    """Verify session cookie and return parsed data, or None if invalid.

    Returns dict with keys: user_id, role, nonce, ts
    """
    secret = _get_session_secret()
    if not secret or not value:
        return None
    parts = value.split(".")
    if len(parts) != 2:
        return None
    payload_b64, sig = parts[0], parts[1]
    expected = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        data = json.loads(payload_json)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    # Check required fields
    if "u" not in data or "t" not in data:
        return None

    # Check expiry
    try:
        ts = int(data["t"])
    except (ValueError, TypeError):
        return None
    try:
        max_age_hours = int(os.getenv("ADMIN_SESSION_MAX_AGE_HOURS", str(SESSION_MAX_AGE_HOURS_DEFAULT)))
    except ValueError:
        max_age_hours = SESSION_MAX_AGE_HOURS_DEFAULT
    if time.time() - ts > max_age_hours * 3600:
        return None

    return {
        "user_id": data["u"],
        "role": data.get("r", "user"),
        "nonce": data.get("n", ""),
        "ts": ts,
    }


def get_session_user_id(request) -> Optional[int]:
    """Extract user_id from session cookie in request."""
    cookie_val = request.cookies.get(COOKIE_NAME) if hasattr(request, "cookies") else None
    if not cookie_val:
        return None
    session_data = verify_session(cookie_val)
    if not session_data:
        return None
    return session_data.get("user_id")


def get_session_user_role(request) -> Optional[str]:
    """Extract user role from session cookie in request."""
    cookie_val = request.cookies.get(COOKIE_NAME) if hasattr(request, "cookies") else None
    if not cookie_val:
        return None
    session_data = verify_session(cookie_val)
    if not session_data:
        return None
    return session_data.get("role")


def is_admin_request(request) -> bool:
    """Check if the current request is from an admin user."""
    return get_session_user_role(request) == "admin"


# ------------------------------------------------------------------
# User management (database-backed)
# ------------------------------------------------------------------

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Look up a user by username. Returns user dict or None."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
    except Exception as e:
        logger.error("Failed to get user by username: %s", e)
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Look up a user by ID. Returns user dict or None."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
    except Exception as e:
        logger.error("Failed to get user by id: %s", e)
        return None


def create_user(username: str, password: str, role: str = "user", email: Optional[str] = None) -> Tuple[Optional[int], Optional[str]]:
    """Create a new user. Returns (user_id, error_message)."""
    err = _validate_username(username)
    if err:
        return None, err
    err = _validate_password(password)
    if err:
        return None, err

    if role not in ("admin", "user"):
        return None, "无效的用户角色"

    # Check if username already exists
    existing = get_user_by_username(username)
    if existing:
        return None, "用户名已存在"

    try:
        from src.storage import get_db, User
        db = get_db()
        pw_hash = hash_password(password)
        with db.session_scope() as session:
            user = User(
                username=username,
                email=email,
                password_hash=pw_hash,
                role=role,
                is_active=True,
            )
            session.add(user)
            session.flush()
            user_id = user.id
        return user_id, None
    except Exception as e:
        logger.error("Failed to create user: %s", e)
        return None, "创建用户失败"


def list_users() -> list:
    """List all users. Returns list of user dicts."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.get_session() as session:
            users = session.query(User).order_by(User.id).all()
            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "isActive": u.is_active,
                    "createdAt": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ]
    except Exception as e:
        logger.error("Failed to list users: %s", e)
        return []


def update_user(user_id: int, **kwargs) -> Optional[str]:
    """Update user fields. Returns error message or None on success."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return "用户不存在"

            if "role" in kwargs:
                if kwargs["role"] not in ("admin", "user"):
                    return "无效的用户角色"
                user.role = kwargs["role"]

            if "email" in kwargs:
                user.email = kwargs["email"]

            if "is_active" in kwargs:
                user.is_active = kwargs["is_active"]

            if "password" in kwargs:
                err = _validate_password(kwargs["password"])
                if err:
                    return err
                user.password_hash = hash_password(kwargs["password"])

            user.updated_at = datetime.now()
        return None
    except Exception as e:
        logger.error("Failed to update user: %s", e)
        return "更新用户失败"


def delete_user(user_id: int) -> Optional[str]:
    """Delete a user. Returns error message or None on success."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return "用户不存在"
            if user.role == "admin":
                # Check if this is the last admin
                admin_count = session.query(User).filter(
                    User.role == "admin",
                    User.is_active == True,
                ).count()
                if admin_count <= 1:
                    return "不能删除最后一个管理员"
            session.delete(user)
        return None
    except Exception as e:
        logger.error("Failed to delete user: %s", e)
        return "删除用户失败"


# ------------------------------------------------------------------
# Migration: ensure admin user exists from legacy file-based password
# ------------------------------------------------------------------

def ensure_admin_user() -> None:
    """Ensure at least one admin user exists. Migrate from legacy file-based password if needed."""
    try:
        from src.storage import get_db, User
        db = get_db()
        with db.get_session() as session:
            admin_count = session.query(User).filter(User.role == "admin").count()
            if admin_count > 0:
                return

            # No admin user exists — try to migrate from legacy file
            cred_path = _get_credential_path()
            if not cred_path.exists():
                # Create default admin with a random password (must be set via CLI)
                logger.warning("No admin user found and no legacy password file. Creating default admin.")
                pw_hash = hash_password(secrets.token_urlsafe(16))
                user = User(
                    username="admin",
                    password_hash=pw_hash,
                    role="admin",
                    is_active=True,
                )
                session.add(user)
                session.flush()
                logger.info("Default admin user created. Use CLI to reset password: python -m src.auth reset_password")
                return

            # Migrate from file-based password
            try:
                raw = cred_path.read_text().strip()
                if raw and ":" in raw:
                    user = User(
                        username="admin",
                        password_hash=raw,
                        role="admin",
                        is_active=True,
                    )
                    session.add(user)
                    session.flush()
                    logger.info("Migrated admin user from legacy password file (user_id=%s)", user.id)
            except Exception as e:
                logger.error("Failed to migrate admin from legacy file: %s", e)
    except Exception as e:
        logger.error("Failed to ensure admin user: %s", e)


# ------------------------------------------------------------------
# Rate limiting & IP utilities
# ------------------------------------------------------------------

def get_client_ip(request) -> str:
    """Get client IP, respecting TRUST_X_FORWARDED_FOR."""
    if os.getenv("TRUST_X_FORWARDED_FOR", "false").lower() == "true":
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    if request.client:
        return request.client.host or "127.0.0.1"
    return "127.0.0.1"


def check_rate_limit(ip: str) -> bool:
    """Return True if under limit, False if rate limited."""
    lock = _get_lock()
    now = time.time()
    with lock:
        expired_keys = [k for k, (_, ts) in _rate_limit.items() if now - ts > RATE_LIMIT_WINDOW_SEC]
        for k in expired_keys:
            del _rate_limit[k]
        if ip in _rate_limit:
            count, first_ts = _rate_limit[ip]
            if count >= RATE_LIMIT_MAX_FAILURES:
                return False
        return True


def record_login_failure(ip: str) -> None:
    """Record a failed login attempt for rate limiting."""
    lock = _get_lock()
    now = time.time()
    with lock:
        if ip in _rate_limit:
            count, first_ts = _rate_limit[ip]
            if now - first_ts > RATE_LIMIT_WINDOW_SEC:
                _rate_limit[ip] = (1, now)
            else:
                _rate_limit[ip] = (count + 1, first_ts)
        else:
            _rate_limit[ip] = (1, now)


def clear_rate_limit(ip: str) -> None:
    """Clear rate limit for IP after successful login."""
    lock = _get_lock()
    with lock:
        _rate_limit.pop(ip, None)


# ------------------------------------------------------------------
# Login / change password (multi-user)
# ------------------------------------------------------------------

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user by username and password. Returns user dict or None."""
    user = get_user_by_username(username)
    if user is None:
        return None
    if not user["is_active"]:
        return None
    if not verify_password_hash(password, user["password_hash"]):
        return None
    return user


def change_user_password(user_id: int, current_password: str, new_password: str) -> Optional[str]:
    """Change a user's password. Verifies current password first. Returns error or None."""
    user = get_user_by_id(user_id)
    if user is None:
        return "用户不存在"
    if not verify_password_hash(current_password, user["password_hash"]):
        return "当前密码错误"
    err = _validate_password(new_password)
    if err:
        return err
    return update_user(user_id, password=new_password)


def admin_reset_user_password(admin_id: int, target_user_id: int, new_password: str) -> Optional[str]:
    """Admin resets a user's password. No current password required. Returns error or None."""
    admin = get_user_by_id(admin_id)
    if admin is None or admin["role"] != "admin":
        return "只有管理员可以重置密码"
    err = _validate_password(new_password)
    if err:
        return err
    return update_user(target_user_id, password=new_password)


# ------------------------------------------------------------------
# Legacy compatibility (for old single-admin endpoints)
# ------------------------------------------------------------------

def verify_password(password: str) -> bool:
    """Legacy: verify password against admin user. For backward compat."""
    if not is_auth_enabled():
        return True
    user = get_user_by_username("admin")
    if user is None:
        return False
    if not user["is_active"]:
        return False
    return verify_password_hash(password, user["password_hash"])


def set_initial_password(password: str) -> Optional[str]:
    """Legacy: set initial admin password. Creates admin user if not exists."""
    err = _validate_password(password)
    if err:
        return err

    try:
        from src.storage import get_db, User
        db = get_db()
        with db.session_scope() as session:
            existing = session.query(User).filter(User.username == "admin").first()
            if existing:
                return "管理员用户已存在"
            user = User(
                username="admin",
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
            session.add(user)
        return None
    except Exception as e:
        logger.error("Failed to set initial password: %s", e)
        return "设置密码失败"


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def reset_password_cli() -> int:
    """Interactive CLI to reset admin password. Returns exit code."""
    _ensure_env_loaded()
    if not _is_auth_enabled_from_env():
        print("Error: Auth is not enabled. Set ADMIN_AUTH_ENABLED=true in .env", file=sys.stderr)
        return 1

    print("Enter new admin password (will not echo):", end=" ")
    pwd = getpass.getpass("")
    err = _validate_password(pwd)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print("Confirm new password:", end=" ")
    pwd2 = getpass.getpass("")
    if pwd != pwd2:
        print("Error: Passwords do not match", file=sys.stderr)
        return 1

    # Update admin user password
    user = get_user_by_username("admin")
    if user:
        result = update_user(user["id"], password=pwd)
        if result:
            print(f"Error: {result}", file=sys.stderr)
            return 1
    else:
        result = set_initial_password(pwd)
        if result:
            print(f"Error: {result}", file=sys.stderr)
            return 1

    print("Password has been reset successfully.")
    return 0


def _main() -> int:
    """CLI entry: reset_password subcommand."""
    if len(sys.argv) > 1 and sys.argv[1] == "reset_password":
        return reset_password_cli()
    print("Usage: python -m src.auth reset_password", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main())
