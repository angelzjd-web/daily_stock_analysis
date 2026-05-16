# -*- coding: utf-8 -*-
"""Points query endpoints — balance and transaction history for the current user."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.deps import get_current_user_id
from src.auth import is_auth_enabled
from src.points import get_points_balance, get_point_transactions, is_points_insufficient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/points", tags=["points"])


@router.get(
    "/balance",
    summary="Get current user points balance",
    description="Returns the authenticated user's points balance.",
)
async def get_balance(request: Request):
    """Get current user's points balance."""
    user_id = get_current_user_id(request)
    if not user_id or not is_auth_enabled():
        return JSONResponse(content={"balance": 0})

    balance = get_points_balance(user_id)
    insufficient = is_points_insufficient(user_id)
    return JSONResponse(content={
        "balance": balance,
        "insufficient": insufficient,
    })


@router.get(
    "/transactions",
    summary="Get current user point transactions",
    description="Returns recent point transaction history for the authenticated user.",
)
async def get_transactions(request: Request, limit: int = 20):
    """Get current user's point transaction history."""
    user_id = get_current_user_id(request)
    if not user_id or not is_auth_enabled():
        return JSONResponse(content={"transactions": []})

    transactions = get_point_transactions(user_id, limit=limit)
    return JSONResponse(content={"transactions": transactions})
