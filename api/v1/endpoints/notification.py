# -*- coding: utf-8 -*-
"""用户通知渠道配置 API 端点。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import get_current_user_id, get_database_manager
from api.v1.schemas.common import ErrorResponse
from src.auth import is_auth_enabled
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


# ────────────── Schemas (inline) ──────────────

from pydantic import BaseModel


class NotificationConfigItem(BaseModel):
    key: str
    value: str


class UpdateNotificationConfigRequest(BaseModel):
    items: list[NotificationConfigItem]


class NotificationConfigResponse(BaseModel):
    items: list[NotificationConfigItem]
    updated_at: Optional[str] = None


class UpdateNotificationConfigResponse(BaseModel):
    success: bool
    count: int


class DeleteNotificationConfigResponse(BaseModel):
    success: bool
    deleted: bool


# ────────────── Endpoints ──────────────


def _get_user_id(request: Request) -> Optional[int]:
    """获取当前登录用户的 user_id。

    - 认证开启时：未登录抛 401
    - 认证关闭时：返回 None（使用默认 user_id=1）
    """
    user_id = get_current_user_id(request)
    if user_id is not None:
        return user_id
    # 认证关闭时，使用默认管理员 user_id
    if not is_auth_enabled():
        return 1
    raise HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "需要登录才能访问通知渠道配置"},
    )


@router.get(
    "/config",
    response_model=NotificationConfigResponse,
    responses={
        401: {"description": "未登录", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取当前用户的通知渠道配置",
    description="返回当前登录用户的所有通知渠道配置项。数据按 user_id 隔离。",
)
def get_notification_config(
    request: Request,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> NotificationConfigResponse:
    user_id = _get_user_id(request)
    try:
        rows = db_manager.get_user_notification_config(user_id)
        items = [NotificationConfigItem(key=r["key"], value=r["value"]) for r in rows]
        updated_at = rows[-1]["updated_at"] if rows else None
        return NotificationConfigResponse(items=items, updated_at=updated_at)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取通知渠道配置失败: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "获取通知渠道配置失败"},
        )


@router.put(
    "/config",
    response_model=UpdateNotificationConfigResponse,
    responses={
        401: {"description": "未登录", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="更新当前用户的通知渠道配置",
    description="批量更新当前登录用户的通知渠道配置项（upsert）。数据按 user_id 隔离。",
)
def update_notification_config(
    body: UpdateNotificationConfigRequest,
    request: Request,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> UpdateNotificationConfigResponse:
    user_id = _get_user_id(request)
    try:
        count = db_manager.set_user_notification_config(
            user_id, [item.model_dump() for item in body.items]
        )
        return UpdateNotificationConfigResponse(success=True, count=count)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("更新通知渠道配置失败: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "更新通知渠道配置失败"},
        )


@router.delete(
    "/config/{key:path}",
    response_model=DeleteNotificationConfigResponse,
    responses={
        401: {"description": "未登录", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="删除当前用户的某项通知渠道配置",
    description="删除当前登录用户指定 key 的通知配置项。数据按 user_id 隔离。",
)
def delete_notification_config(
    key: str,
    request: Request,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> DeleteNotificationConfigResponse:
    user_id = _get_user_id(request)
    try:
        deleted = db_manager.delete_user_notification_config(user_id, key)
        return DeleteNotificationConfigResponse(success=True, deleted=deleted)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("删除通知渠道配置失败: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "删除通知渠道配置失败"},
        )
