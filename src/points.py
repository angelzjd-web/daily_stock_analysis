# -*- coding: utf-8 -*-
"""
Points system service — deduct, query, and admin-manage user points.

Behaviour:
- Analysis costs 5 points, Agent chat costs 20 points.
- Insufficient balance blocks the operation (returns error).
- Auth-disabled mode skips all point operations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# --- Constants ---

COST_ANALYSIS = 5
COST_AGENT = 20
COST_RESEARCH = 30
COST_MX_DATA = 2

TX_TYPE_ANALYSIS = "analysis"
TX_TYPE_AGENT = "agent"
TX_TYPE_RESEARCH = "research"
TX_TYPE_MX_DATA = "mx_data"
TX_TYPE_ADMIN_GRANT = "admin_grant"
TX_TYPE_ADMIN_DEDUCT = "admin_deduct"


# --- Helpers ---

def _is_auth_enabled() -> bool:
    """Check if auth is enabled (points only matter when auth is on)."""
    from src.auth import is_auth_enabled
    return is_auth_enabled()


def _get_db():
    """Lazy-import DatabaseManager."""
    from src.storage import get_db
    return get_db()


# --- Core functions ---

def deduct_points(user_id: int, amount: int, tx_type: str, description: str = "") -> bool:
    """
    Deduct points from a user after a successful operation.
    Returns True on success, False on failure.
    No-op when auth is disabled or user_id is None.
    """
    if not user_id or not _is_auth_enabled():
        return True

    try:
        from src.storage import User, PointTransaction
        db = _get_db()
        with db.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                logger.warning("deduct_points: user %s not found", user_id)
                return False

            old_balance = user.points_balance or 0
            new_balance = old_balance - amount
            user.points_balance = new_balance
            user.updated_at = datetime.now()

            tx = PointTransaction(
                user_id=user_id,
                change=-amount,
                balance_after=new_balance,
                type=tx_type,
                description=description,
            )
            session.add(tx)

        logger.info(
            "Points deducted: user=%s, amount=%s, balance %s->%s, type=%s",
            user_id, amount, old_balance, new_balance, tx_type,
        )
        return True
    except Exception as e:
        logger.error("deduct_points failed: %s", e)
        return False


def check_points_sufficient(user_id: Optional[int], amount: int) -> tuple[bool, int]:
    """
    Check if user has enough points for an operation.
    Returns (is_sufficient, current_balance).
    Always returns (True, 0) when auth is disabled or user_id is None.
    """
    balance = get_points_balance(user_id)
    return (balance >= amount, balance)


def get_points_balance(user_id: Optional[int]) -> int:
    """Return current points balance for a user.  0 if auth disabled or no user."""
    if not user_id or not _is_auth_enabled():
        return 0

    try:
        from src.storage import User
        db = _get_db()
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return 0
            return user.points_balance or 0
    except Exception as e:
        logger.error("get_points_balance failed: %s", e)
        return 0


def is_points_insufficient(user_id: Optional[int], min_amount: int = 1) -> bool:
    """Return True if user's balance is less than min_amount (default 1)."""
    return get_points_balance(user_id) < min_amount


def admin_set_points(user_id: int, new_balance: int, reason: str = "") -> Optional[str]:
    """
    Admin sets a user's points balance to a specific value.
    Returns error message or None on success.
    """
    try:
        from src.storage import User, PointTransaction
        db = _get_db()
        with db.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return "用户不存在"

            old_balance = user.points_balance or 0
            change = new_balance - old_balance
            user.points_balance = new_balance
            user.updated_at = datetime.now()

            tx_type = TX_TYPE_ADMIN_GRANT if change >= 0 else TX_TYPE_ADMIN_DEDUCT
            tx = PointTransaction(
                user_id=user_id,
                change=change,
                balance_after=new_balance,
                type=tx_type,
                description=reason or f"管理员设置积分为 {new_balance}",
            )
            session.add(tx)

        logger.info(
            "Admin set points: user=%s, %s->%s (change=%s), reason=%s",
            user_id, old_balance, new_balance, change, reason,
        )
        return None
    except Exception as e:
        logger.error("admin_set_points failed: %s", e)
        return "设置积分失败"


def get_point_transactions(user_id: Optional[int], limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent point transactions for a user."""
    if not user_id or not _is_auth_enabled():
        return []

    try:
        from src.storage import PointTransaction
        db = _get_db()
        with db.get_session() as session:
            txs = (
                session.query(PointTransaction)
                .filter(PointTransaction.user_id == user_id)
                .order_by(PointTransaction.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "change": t.change,
                    "balanceAfter": t.balance_after,
                    "type": t.type,
                    "description": t.description,
                    "createdAt": t.created_at.isoformat() if t.created_at else None,
                }
                for t in txs
            ]
    except Exception as e:
        logger.error("get_point_transactions failed: %s", e)
        return []
