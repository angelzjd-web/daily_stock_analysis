# -*- coding: utf-8 -*-
"""
===================================
API 依赖注入模块
===================================

职责：
1. 提供数据库 Session 依赖
2. 提供配置依赖
3. 提供服务层依赖
4. 提供当前用户信息依赖
"""

from typing import Generator, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from src.storage import DatabaseManager
from src.config import get_config, Config
from src.services.system_config_service import SystemConfigService


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库 Session 依赖
    
    使用 FastAPI 依赖注入机制，确保请求结束后自动关闭 Session
    
    Yields:
        Session: SQLAlchemy Session 对象
        
    Example:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            ...
    """
    db_manager = DatabaseManager.get_instance()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def get_config_dep() -> Config:
    """
    获取配置依赖
    
    Returns:
        Config: 配置单例对象
    """
    return get_config()


def get_database_manager() -> DatabaseManager:
    """
    获取数据库管理器依赖
    
    Returns:
        DatabaseManager: 数据库管理器单例对象
    """
    return DatabaseManager.get_instance()


def get_system_config_service(request: Request) -> SystemConfigService:
    """Get app-lifecycle shared SystemConfigService instance."""
    service = getattr(request.app.state, "system_config_service", None)
    if service is None:
        service = SystemConfigService()
        request.app.state.system_config_service = service
    return service


def get_current_user_id(request: Request) -> Optional[int]:
    """Get the current authenticated user's ID from request state.
    
    Returns None if auth is disabled or no user is logged in.
    """
    return getattr(request.state, "user_id", None)


def get_current_user_role(request: Request) -> Optional[str]:
    """Get the current authenticated user's role from request state.
    
    Returns None if auth is disabled or no user is logged in.
    """
    return getattr(request.state, "user_role", None)


def require_user_id(request: Request) -> int:
    """Get the current user's ID, raising 401 if not authenticated.
    
    Use this for endpoints that always require authentication.
    """
    user_id = get_current_user_id(request)
    if user_id is None:
        from fastapi.responses import JSONResponse
        raise ValueError("Authentication required")
    return user_id
