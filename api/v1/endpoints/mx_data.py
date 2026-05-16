# -*- coding: utf-8 -*-
"""
东方财富妙想 API 数据端点

提供以下能力：
1. 金融数据自然语言查询 (mx-finance-data)
2. 金融资讯搜索 (mx-finance-search)
3. 宏观经济数据查询 (mx-macro-data)
4. 选股/选板块/选基金 (mx-stocks-screener)
5. 业绩点评 (stock-earnings-review)
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from api.deps import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mx", tags=["东方财富妙想数据"])


@router.post("/finance-data", summary="金融数据查询")
async def query_finance_data(request: Request, body: dict):
    """
    金融数据自然语言查询。

    支持查询：实时行情、K线数据、基本面、资金流向、筹码分布等。
    覆盖：A股、港股、美股、基金、债券、板块。

    Body:
        query: 自然语言查询文本
    """
    user_id = get_current_user_id(request)
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    from data_provider.mx_api.finance_data import query_mx_finance_data

    try:
        result = await query_mx_finance_data(query=query)
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return {"data": result, "query": query}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[mx-finance-data] 查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/finance-search", summary="金融资讯搜索")
async def search_finance_news(request: Request, body: dict):
    """
    金融资讯自然语言搜索。

    支持搜索：新闻、研报、公告、交易所动态、政策等。
    覆盖：全球市场。

    Body:
        query: 自然语言搜索文本
    """
    user_id = get_current_user_id(request)
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    from data_provider.mx_api.finance_search import query_financial_news

    try:
        result = await query_financial_news(query=query, save_to_file=False)
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return {"data": result, "query": query}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[mx-finance-search] 搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macro-data", summary="宏观经济数据查询")
async def query_macro_data(request: Request, body: dict):
    """
    宏观经济数据自然语言查询。

    支持查询：GDP、CPI、PPI、PMI、M2、社融、利率、汇率、商品价格等。
    覆盖：全球主要经济体。

    Body:
        query: 自然语言查询文本
    """
    user_id = get_current_user_id(request)
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    from data_provider.mx_api.macro_data import query_mx_macro_data

    try:
        result = await query_mx_macro_data(query=query)
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return {"data": result, "query": query}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[mx-macro-data] 查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks-screener", summary="选股/选板块/选基金")
async def screen_stocks(request: Request, body: dict):
    """
    通过自然语言进行选股、选板块、选基金。

    支持：A股、港股、美股、基金、ETF、可转债、板块筛选。

    Body:
        query: 自然语言查询条件
        select_type: 标的类型（A股/港股/美股/基金/ETF/可转债/板块）
    """
    user_id = get_current_user_id(request)
    query = body.get("query", "").strip()
    select_type = body.get("select_type", "A股").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    valid_types = {"A股", "港股", "美股", "基金", "ETF", "可转债", "板块"}
    if select_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"select_type 必须为: {', '.join(sorted(valid_types))}",
        )

    from data_provider.mx_api.stocks_screener import query_mx_stocks_screener

    output_dir = Path.cwd() / "miaoxiang" / "mx_stocks_screener"

    try:
        result = await query_mx_stocks_screener(
            query=query, selectType=select_type, output_dir=output_dir
        )
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return {"data": result, "query": query, "select_type": select_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[mx-stocks-screener] 筛选失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
