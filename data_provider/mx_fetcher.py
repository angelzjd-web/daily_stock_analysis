# -*- coding: utf-8 -*-
"""
===================================
东方财富妙想 API 数据源
===================================

基于东方财富妙想大模型 API，替换所有原有数据源（akshare/tushare/baostock/efinance/pytdx/yfinance/longbridge）。
提供统一的数据获取接口，与 DataFetcherManager 的公共方法签名完全兼容。

核心 API：
1. searchData      - 金融数据查询（K线、行情、基本面、筹码、资金流向等）
2. searchNews      - 金融资讯搜索（新闻、研报、公告）
3. searchMacroData - 宏观经济数据查询
4. selectSecurity  - 选股/选板块/选基金

使用方式：
    MXFetcher 实例化后可直接替代 DataFetcherManager 的数据源循环逻辑，
    无需修改上层调用代码。
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# === API 配置 ===
EM_API_KEY = os.environ.get("EM_API_KEY", "em_twy8iqm1jeU4skJvkc3P6GrMz7r8Aiou").strip()
EM_API_BASE = "https://ai-saas.eastmoney.com"
SEARCH_DATA_URL = f"{EM_API_BASE}/proxy/b/mcp/tool/searchData"
SEARCH_NEWS_URL = f"{EM_API_BASE}/proxy/b/mcp/tool/searchNews"
SEARCH_MACRO_URL = f"{EM_API_BASE}/proxy/b/mcp/tool/searchMacroData"
SELECT_SECURITY_URL = f"{EM_API_BASE}/proxy/b/mcp/tool/selectSecurity"
DEFAULT_TIMEOUT = 30.0

# === 标准 K 线列名 ===
STANDARD_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]


def _build_request_body(query: str, **extra: Any) -> Dict[str, Any]:
    """构建统一的请求体。"""
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    body: Dict[str, Any] = {
        "query": query,
        "toolContext": {
            "callId": call_id,
            "userInfo": {"userId": user_id},
        },
    }
    body.update(extra)
    return body


async def _mx_api_call(
    url: str,
    query: str,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> Dict[str, Any]:
    """
    统一 API 调用入口。

    Args:
        url: API 端点 URL
        query: 自然语言查询
        timeout: 超时秒数
        **extra: 额外请求体字段

    Returns:
        接口返回的 data 字段（已解包）
    """
    body = _build_request_body(query, **extra)
    headers = {
        "Content-Type": "application/json",
        "em_api_key": EM_API_KEY,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    if not isinstance(payload, dict):
        return {"error": f"接口返回非 JSON 对象: {type(payload).__name__}"}

    # 业务状态校验
    code = payload.get("code")
    status = payload.get("status")
    success_values = (None, 0, 200, "0", "200")
    if code not in success_values or status not in success_values:
        msg = payload.get("message") or payload.get("msg") or "业务状态非成功"
        return {"error": f"接口错误: code={code}, status={status}, message={msg}"}

    # 解包 data 节点
    data = payload.get("data")
    if isinstance(data, dict):
        # 检查 data.message 提示
        data_msg = data.get("message")
        if isinstance(data_msg, str) and data_msg.strip():
            data["_mx_message"] = data_msg.strip()
        return data

    return payload


def _extract_data_table_dto_list(api_result: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    """
    从 searchData 接口返回中提取 dataTableDTOList。

    兼容:
    - 新结构 data.searchDataResultDTO.dataTableDTOList
    - 旧结构 dataTableDTOList / data.dataTableDTOList
    """
    if not isinstance(api_result, dict):
        return None, "接口返回不是 JSON 对象"

    dto_list = api_result.get("dataTableDTOList")
    if isinstance(dto_list, list):
        return dto_list, None

    search_result = api_result.get("searchDataResultDTO")
    if isinstance(search_result, dict):
        dto_list = search_result.get("dataTableDTOList")
        if isinstance(dto_list, list):
            return dto_list, None

    return None, "接口返回中无 dataTableDTOList"


def _flatten_value(v: Any) -> str:
    """将任意值规范为字符串表示。"""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _dto_table_to_dataframe(dto: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    将单个 dataTableDTO 块转换为 DataFrame。

    处理 table 字段中的 headName + 指标键/值对结构。
    """
    table = dto.get("table") or {}
    name_map = dto.get("nameMap") or {}
    if isinstance(name_map, list):
        name_map = {str(i): v for i, v in enumerate(name_map)}
    elif not isinstance(name_map, dict):
        name_map = {}

    if not isinstance(table, dict):
        # 通用 list 结构
        if isinstance(table, list) and table:
            if isinstance(table[0], dict):
                rows = [{_flatten_value(k): _flatten_value(v) for k, v in row.items()} for row in table]
            else:
                rows = [dict(zip([f"col_{i}" for i in range(len(row))], [_flatten_value(v) for v in row])) for row in table]
            return pd.DataFrame(rows) if rows else None
        return None

    headers = table.get("headName") or []
    if not isinstance(headers, list):
        headers = []

    entity_name = _flatten_value(dto.get("entityName") or "")

    # 获取非 headName 的数据键（即指标键）
    data_keys = [k for k in table.keys() if k != "headName"]
    if not data_keys or not headers:
        return None

    rows = []
    if len(headers) > 1:
        fieldnames = [entity_name or "指标"] + [_flatten_value(h) for h in headers]
        for key in data_keys:
            raw_values = table.get(key, [])
            if not isinstance(raw_values, list):
                raw_values = [raw_values]
            values = [_flatten_value(v) for v in raw_values]
            # 补齐列数
            if len(values) < len(headers):
                values.extend([""] * (len(headers) - len(values)))
            values = values[: len(headers)]

            # 指标名称
            label = name_map.get(str(key)) or name_map.get(key) or _flatten_value(key)
            if isinstance(label, (dict, list)):
                label = _flatten_value(label)
            row = dict(zip(fieldnames, [label] + values))
            rows.append(row)
    elif len(headers) == 1:
        fieldnames = [entity_name or "指标", _flatten_value(headers[0])]
        for key in data_keys:
            raw_values = table.get(key, [])
            value = raw_values[0] if isinstance(raw_values, list) and raw_values else raw_values
            label = name_map.get(str(key)) or name_map.get(key) or _flatten_value(key)
            if isinstance(label, (dict, list)):
                label = _flatten_value(label)
            row = {fieldnames[0]: label, fieldnames[1]: _flatten_value(value)}
            rows.append(row)

    return pd.DataFrame(rows) if rows else None


def _extract_news_content(api_result: Any) -> str:
    """从 searchNews 接口返回中提取可读文本。"""
    if not isinstance(api_result, dict):
        return ""

    for wrapper_key in ("data", "result"):
        wrapped = api_result.get(wrapper_key)
        if isinstance(wrapped, dict):
            nested = _extract_news_content(wrapped)
            if nested:
                return nested

    for key in ("llmSearchResponse", "searchResponse", "content", "answer", "summary"):
        value = api_result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False, indent=2)

    return json.dumps(api_result, ensure_ascii=False, indent=2) if api_result else ""


def _wide_dto_list_to_daily_dataframe(dto_list: List[Any], stock_code: str) -> Optional[pd.DataFrame]:
    """
    将多个 DTO 的宽格式数据（指标在行、日期在列）透视为标准日线长格式。

    策略：
    1. 按 DTO 的日度数据行数降序排序（日度 OHLCV 最完整的 DTO 优先）
    2. 核心 OHLCV 指标优先级高于 "区间" 前缀指标
    3. 同一指标已有值时不被低优先级数据覆盖

    Returns:
        标准 K 线 DataFrame，解析失败返回 None
    """
    import re

    # K 线核心指标关键词映射（高优先级，直接覆盖）
    metric_map = {
        "开盘价": "open", "今开": "open", "开盘": "open",
        "最高价": "high", "最高": "high", "区间最高价": "high",
        "最低价": "low", "最低": "low", "区间最低价": "low",
        "收盘价": "close", "收盘": "close", "最新价": "close",
        "成交量": "volume", "成交股数": "volume",
        "成交额": "amount", "成交金额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover_rate",
    }

    # "区间" 前缀指标 → 低优先级，仅回填缺失字段
    range_metric_map = {
        "区间成交量": "volume",
        "区间成交额": "amount",
        "区间涨跌幅": "pct_chg",
        "区间换手率": "turnover_rate",
    }

    # 预处理：给每个 DTO 计算日度日期列数和 OHLCV 指标数
    dto_scores = []
    for idx, dto in enumerate(dto_list):
        if not isinstance(dto, dict):
            continue
        table = dto.get("table") or {}
        if not isinstance(table, dict):
            continue
        headers = table.get("headName") or []
        if not isinstance(headers, list):
            continue

        date_cols = []
        for h in headers:
            h_str = _flatten_value(h)
            match = re.match(r"(\d{4}-\d{2}-\d{2})", h_str)
            if match:
                date_cols.append(match.group(1))

        # 排除月度/快照 DTO（日期列 ≤ 4 的且包含"区间"前缀指标的是月度汇总）
        name_map = dto.get("nameMap") or {}
        data_keys = [k for k in table.keys() if k != "headName"]
        has_ohlc = False
        ohlcv_count = 0
        for key in data_keys:
            label = name_map.get(key) or str(key)
            if isinstance(label, (dict, list)):
                label = _flatten_value(label)
            for cn_name in ["开盘价", "收盘价", "最低价", "最高价"]:
                if cn_name in label:
                    ohlcv_count += 1
                    break
        if ohlcv_count >= 3:
            has_ohlc = True

        dto_scores.append((idx, len(date_cols), has_ohlc))

    # 排序：日度日期列多 + 包含 OHLCV 的 DTO 优先
    dto_scores.sort(key=lambda x: (x[2], x[1]), reverse=True)

    # 收集所有 {日期: {指标: 值}} 的合并字典
    daily_data: Dict[str, Dict[str, str]] = {}

    for idx, _, _ in dto_scores:
        dto = dto_list[idx]
        table = dto.get("table") or {}
        headers = table.get("headName") or []
        name_map = dto.get("nameMap") or {}
        data_keys = [k for k in table.keys() if k != "headName"]

        for key in data_keys:
            raw_label = str(key)
            label = name_map.get(raw_label) or name_map.get(str(key)) or raw_label
            if isinstance(label, (dict, list)):
                label = _flatten_value(label)

            # 先检查区间指标映射（低优先级）
            metric_en = None
            is_range_metric = False
            for cn_name, en_name in range_metric_map.items():
                if cn_name in label:
                    metric_en = en_name
                    is_range_metric = True
                    break

            # 再检查核心指标映射（高优先级）
            if metric_en is None:
                for cn_name, en_name in metric_map.items():
                    if cn_name in label:
                        metric_en = en_name
                        is_range_metric = False
                        break

            if metric_en is None:
                continue

            values = table.get(key, [])
            if not isinstance(values, list):
                values = [values]

            for i, h in enumerate(headers):
                date_match = re.match(r"(\d{4}-\d{2}-\d{2})", _flatten_value(h))
                if not date_match:
                    continue
                date_str = date_match.group(1)
                val = values[i] if i < len(values) else None
                if date_str not in daily_data:
                    daily_data[date_str] = {}
                # 区间指标仅回填：不覆盖已有核心数据
                if is_range_metric and metric_en in daily_data[date_str]:
                    continue
                daily_data[date_str][metric_en] = _flatten_value(val)

    if not daily_data:
        return None

    # 构建标准 DataFrame
    rows = []
    for date_str in sorted(daily_data.keys()):
        d = daily_data[date_str]
        row = {"date": date_str}
        for col in STANDARD_COLUMNS:
            if col != "date":
                row[col] = d.get(col, "")
        rows.append(row)

    df = pd.DataFrame(rows)
    return df if not df.empty else None


class MXFetcher:
    """
    东方财富妙想 API 数据源。

    替代所有原有数据源（akshare/tushare/baostock/efinance/pytdx/yfinance/longbridge），
    通过自然语言查询获取结构化金融数据。

    公共方法与 DataFetcherManager 完全兼容，可直接替换使用。
    """

    name: str = "MXFetcher"
    priority: int = 0  # 最高优先级

    def __init__(self) -> None:
        self._stock_name_cache: Dict[str, str] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        api_key = EM_API_KEY
        if not api_key:
            logger.warning("[MXFetcher] EM_API_KEY 未配置，数据查询将失败")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """获取或创建事件循环。"""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
                if self._loop.is_closed():
                    raise RuntimeError("closed")
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        """在同步上下文中运行异步协程。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中（如 FastAPI），使用 nest_asyncio 或新线程
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=60)
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ================================================================
    # 核心数据查询方法 — 对应 DataFetcherManager 的公共接口
    # ================================================================

    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30,
    ) -> Tuple[pd.DataFrame, str]:
        """
        获取日线数据。

        通过 mx-finance-data API 查询 K 线行情数据，返回标准化的 DataFrame。

        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            days: 获取天数

        Returns:
            Tuple[DataFrame, str]: (标准化K线数据, 数据源名称"MXFetcher")
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days * 2)
            start_date = start_dt.strftime("%Y-%m-%d")

        # 构建查询（措辞优化：先日度行情，再补充K线字段）
        # 策略：用两个查询补充
        # 查询1：日度行情数据（API 返回包含 OHLCV 的宽格式 DTO）
        query = f"{stock_code} 日线行情 最近{days + 30}天"

        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
        except Exception as e:
            raise DataFetchError(f"[MXFetcher] {stock_code} 日线查询失败: {e}") from e

        if "error" in result:
            raise DataFetchError(f"[MXFetcher] {stock_code} 日线查询失败: {result['error']}")

        dto_list, err = _extract_data_table_dto_list(result)
        if err or not dto_list:
            raise DataFetchError(f"[MXFetcher] {stock_code} 日线数据解析失败: {err or 'dataTableDTOList 为空'}")

        # 优先使用宽格式转长格式（K 线数据通常是宽格式）
        combined = _wide_dto_list_to_daily_dataframe(dto_list, stock_code)

        if combined is None or combined.empty:
            # 回退：通用 DTO 解析
            dfs = []
            for dto in dto_list:
                if not isinstance(dto, dict):
                    continue
                df = _dto_table_to_dataframe(dto)
                if df is not None and not df.empty:
                    dfs.append(df)

            if not dfs:
                raise DataFetchError(f"[MXFetcher] {stock_code} 日线数据为空")

            combined = pd.concat(dfs, ignore_index=True)
            # 标准化列名
            combined = self._normalize_daily_columns(combined)
        # 数据清洗
        combined = self._clean_daily_data(combined)
        # 计算技术指标
        combined = self._calculate_indicators(combined)

        logger.info(f"[MXFetcher] {stock_code} 日线获取成功: rows={len(combined)}")
        return combined, "MXFetcher"

    def get_realtime_quote(self, stock_code: str, **kwargs):
        """
        获取实时行情数据。

        通过 mx-finance-data API 查询实时行情，返回 UnifiedRealtimeQuote 兼容对象。

        Args:
            stock_code: 股票代码

        Returns:
            RealtimeQuote 兼容字典对象，查询失败返回 None
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        query = f"{stock_code} 实时行情，包括最新价、涨跌幅、涨跌额、成交量、成交额、换手率、量比、市盈率、市净率、总市值、流通市值、今开、最高、最低、昨收"

        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
        except Exception as e:
            logger.warning(f"[MXFetcher] {stock_code} 实时行情查询失败: {e}")
            return None

        if "error" in result:
            logger.warning(f"[MXFetcher] {stock_code} 实时行情查询失败: {result['error']}")
            return None

        dto_list, err = _extract_data_table_dto_list(result)
        if err or not dto_list:
            logger.warning(f"[MXFetcher] {stock_code} 实时行情解析失败: {err}")
            return None

        # 从 DTO 提取行情数据
        quote_data = self._parse_realtime_from_dto(dto_list, stock_code)
        return quote_data

    def get_stock_name(self, stock_code: str, **kwargs) -> Optional[str]:
        """
        获取股票中文名称。

        先查缓存，再通过 mx-finance-data 查询。

        Args:
            stock_code: 股票代码

        Returns:
            股票名称，失败返回 None
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        # 1. 查缓存
        cached = self._stock_name_cache.get(stock_code)
        if cached:
            return cached

        # 2. 静态映射
        from .base import STOCK_NAME_MAP
        from src.data.stock_mapping import is_meaningful_stock_name
        from src.data.stock_index_loader import get_index_stock_name

        static_name = STOCK_NAME_MAP.get(stock_code)
        if is_meaningful_stock_name(static_name, stock_code):
            self._stock_name_cache[stock_code] = static_name
            return static_name

        index_name = get_index_stock_name(stock_code)
        if is_meaningful_stock_name(index_name, stock_code):
            self._stock_name_cache[stock_code] = index_name
            return index_name

        # 3. 通过 API 查询
        query = f"{stock_code} 公司名称"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" not in result:
                dto_list, _ = _extract_data_table_dto_list(result)
                if dto_list:
                    for dto in dto_list:
                        if isinstance(dto, dict):
                            # 尝试从 entityName 或 table 数据中提取名称
                            entity_name = dto.get("entityName") or ""
                            if entity_name and not entity_name.isdigit():
                                self._stock_name_cache[stock_code] = entity_name
                                return entity_name
                            # 从 table 数据中查找
                            table = dto.get("table") or {}
                            if isinstance(table, dict):
                                for k, v in table.items():
                                    if k == "headName":
                                        continue
                                    if isinstance(v, list) and v:
                                        val = v[0]
                                        if isinstance(val, str) and val and not val.isdigit():
                                            self._stock_name_cache[stock_code] = val
                                            return val
        except Exception as e:
            logger.debug(f"[MXFetcher] {stock_code} 名称查询失败: {e}")

        return ""

    def get_chip_distribution(self, stock_code: str) -> Optional[Any]:
        """
        获取筹码分布数据。

        Args:
            stock_code: 股票代码

        Returns:
            ChipDistribution 对象或 None
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        query = f"{stock_code} 筹码分布"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                logger.warning(f"[MXFetcher] {stock_code} 筹码分布查询失败: {result['error']}")
                return None

            dto_list, _ = _extract_data_table_dto_list(result)
            if dto_list:
                # 解析筹码分布数据为 ChipDistribution 兼容结构
                return self._parse_chip_from_dto(dto_list, stock_code)
        except Exception as e:
            logger.warning(f"[MXFetcher] {stock_code} 筹码分布查询失败: {e}")

        return None

    def get_fundamental_context(self, stock_code: str, budget_seconds: Optional[float] = None, **kwargs) -> Dict[str, Any]:
        """
        获取基本面上下文数据。

        Args:
            stock_code: 股票代码
            budget_seconds: 预算时间（忽略，API 自带超时）

        Returns:
            基本面数据字典
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        query = f"{stock_code} 基本面数据，包括市盈率、市净率、ROE、营收、净利润、毛利率、净利率、资产负债率、每股收益、每股净资产、总股本、流通股本"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return self.build_failed_fundamental_context(stock_code, result["error"])

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return self.build_failed_fundamental_context(stock_code, "dataTableDTOList 为空")

            # 将 DTO 数据转换为基本面上下文字典
            context = {"stock_code": stock_code, "source": "MXFetcher"}
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None:
                        # 将 DataFrame 转为字典列表存入 context
                        entity_name = dto.get("entityName") or "基本面"
                        context[entity_name] = df.to_dict(orient="records")

            return context
        except Exception as e:
            return self.build_failed_fundamental_context(stock_code, str(e))

    @staticmethod
    def build_failed_fundamental_context(stock_code: str, reason: str) -> Dict[str, Any]:
        """构建失败的基本面上下文。"""
        return {
            "stock_code": stock_code,
            "source": "MXFetcher",
            "error": reason,
            "fundamental_summary": f"基本面数据获取失败: {reason}",
        }

    def get_belong_boards(self, stock_code: str) -> List[Dict[str, Any]]:
        """
        获取股票所属板块。

        Args:
            stock_code: 股票代码

        Returns:
            板块列表
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        query = f"{stock_code} 所属板块"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return []

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return []

            boards = []
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None:
                        for _, row in df.iterrows():
                            board = {k: str(v) for k, v in row.items()}
                            boards.append(board)
            return boards
        except Exception as e:
            logger.debug(f"[MXFetcher] {stock_code} 所属板块查询失败: {e}")
            return []

    def get_main_indices(self, region: str = "cn") -> List[Dict[str, Any]]:
        """
        获取主要指数实时行情。

        Args:
            region: 市场区域 cn/us

        Returns:
            指数行情列表
        """
        if region == "cn":
            query = "沪深主要指数实时行情，上证指数、深证成指、创业板指、沪深300、中证500、科创50"
        elif region == "us":
            query = "美股主要指数实时行情，道琼斯、纳斯达克、标普500"
        else:
            query = f"主要指数实时行情 region={region}"

        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return []

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return []

            indices = []
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None:
                        for _, row in df.iterrows():
                            index_data = {k: str(v) for k, v in row.items()}
                            indices.append(index_data)
            return indices
        except Exception as e:
            logger.warning(f"[MXFetcher] 指数行情查询失败: {e}")
            return []

    def get_market_stats(self) -> Dict[str, Any]:
        """
        获取市场涨跌统计。

        Returns:
            包含 up_count/down_count/flat_count/limit_up_count/limit_down_count/total_amount 的字典
        """
        query = "A股市场涨跌统计，上涨家数、下跌家数、平盘家数、涨停家数、跌停家数、两市成交额"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return {}

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return {}

            stats = {}
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None and not df.empty:
                        row = df.iloc[0].to_dict()
                        stats.update({k: str(v) for k, v in row.items()})
            return stats
        except Exception as e:
            logger.warning(f"[MXFetcher] 市场统计查询失败: {e}")
            return {}

    def get_sector_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """
        获取板块涨跌榜。

        Args:
            n: 返回前 n 个

        Returns:
            (领涨板块列表, 领跌板块列表)
        """
        query = f"今日涨幅最大的{n}个行业板块和跌幅最大的{n}个行业板块"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return [], []

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return [], []

            all_sectors = []
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None:
                        for _, row in df.iterrows():
                            all_sectors.append({k: str(v) for k, v in row.items()})

            # 简单分割：无法区分涨跌则返回全部
            mid = len(all_sectors) // 2
            return all_sectors[:mid], all_sectors[mid:]
        except Exception as e:
            logger.warning(f"[MXFetcher] 板块排行查询失败: {e}")
            return [], []

    def get_capital_flow_context(self, stock_code: str, **kwargs) -> Dict[str, Any]:
        """
        获取资金流向上下文。

        Args:
            stock_code: 股票代码

        Returns:
            资金流向数据字典
        """
        from .base import normalize_stock_code

        stock_code = normalize_stock_code(stock_code)

        query = f"{stock_code} 资金流向，主力净流入、超大单净流入、大单净流入、中单净流入、小单净流入"
        try:
            result = self._run_async(
                _mx_api_call(SEARCH_DATA_URL, query)
            )
            if "error" in result:
                return {"stock_code": stock_code, "error": result["error"]}

            dto_list, _ = _extract_data_table_dto_list(result)
            if not dto_list:
                return {"stock_code": stock_code, "error": "无资金流向数据"}

            context = {"stock_code": stock_code, "source": "MXFetcher"}
            for dto in dto_list:
                if isinstance(dto, dict):
                    df = _dto_table_to_dataframe(dto)
                    if df is not None:
                        entity = dto.get("entityName") or "资金流向"
                        context[entity] = df.to_dict(orient="records")
            return context
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)}

    def prefetch_stock_names(self, stock_codes: List[str], **kwargs) -> None:
        """批量预取股票名称到缓存。"""
        from .base import normalize_stock_code

        for code in stock_codes:
            code = normalize_stock_code(code)
            if code not in self._stock_name_cache:
                try:
                    name = self.get_stock_name(code)
                    if name:
                        self._stock_name_cache[code] = name
                except Exception:
                    pass

    # ================================================================
    # 妙想 API 新增能力（原有项目不具备）
    # ================================================================

    def search_financial_data(self, query: str, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        金融数据自然语言查询（直接暴露 mx-finance-data API）。

        Args:
            query: 自然语言查询
            output_dir: 输出目录

        Returns:
            查询结果字典
        """
        from .mx_api.finance_data import query_mx_finance_data
        return self._run_async(query_mx_finance_data(query=query, output_dir=output_dir))

    def search_financial_news(self, query: str, save_to_file: bool = False) -> Dict[str, Any]:
        """
        金融资讯自然语言搜索（直接暴露 mx-finance-search API）。

        Args:
            query: 自然语言搜索

        Returns:
            搜索结果字典，含 content 字段
        """
        from .mx_api.finance_search import query_financial_news
        return self._run_async(query_financial_news(query=query, save_to_file=save_to_file))

    def search_macro_data(self, query: str, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        宏观经济数据查询（直接暴露 mx-macro-data API）。

        Args:
            query: 自然语言查询

        Returns:
            查询结果字典
        """
        from .mx_api.macro_data import query_mx_macro_data
        return self._run_async(query_mx_macro_data(query=query, output_dir=output_dir))

    def screen_stocks(self, query: str, select_type: str = "A股", output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        选股/选板块/选基金（直接暴露 mx-stocks-screener API）。

        Args:
            query: 自然语言查询
            select_type: A股/港股/美股/基金/ETF/可转债/板块

        Returns:
            筛选结果字典
        """
        from .mx_api.stocks_screener import query_mx_stocks_screener
        output_dir = output_dir or Path.cwd() / "miaoxiang" / "mx_stocks_screener"
        return self._run_async(query_mx_stocks_screener(query=query, selectType=select_type, output_dir=output_dir))

    # ================================================================
    # 内部辅助方法
    # ================================================================

    @staticmethod
    def _normalize_daily_columns(df: pd.DataFrame) -> pd.DataFrame:
        """将 DataFrame 列名标准化为 STANDARD_COLUMNS 格式。"""
        rename_map = {}
        col_map = {
            "日期": "date", "时间": "date", "交易日期": "date",
            "开盘价": "open", "开盘": "open", "今开": "open",
            "最高价": "high", "最高": "high",
            "最低价": "low", "最低": "low",
            "收盘价": "close", "收盘": "close", "最新价": "close",
            "成交量": "volume", "成交股数": "volume",
            "成交额": "amount", "成交金额": "amount",
            "涨跌幅": "pct_chg", "涨跌": "pct_chg", "涨跌幅(%)": "pct_chg",
        }
        for col in df.columns:
            for cn, en in col_map.items():
                if cn in col or col == cn:
                    rename_map[col] = en
                    break
        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    @staticmethod
    def _clean_daily_data(df: pd.DataFrame) -> pd.DataFrame:
        """清洗日线数据。"""
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # 先清洗带单位的中文数值（如"247.3万股" -> 2473000, "40.43亿" -> 4043000000）
        def _parse_chinese_number(val):
            """解析中文单位数值。"""
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return val
            s = str(val).strip()
            if not s:
                return None
            import re
            # 处理带%的百分比
            m = re.match(r'^(-?[\d.]+)%$', s)
            if m:
                return float(m.group(1))
            # 处理"万股"
            m = re.match(r'^(-?[\d.]+)万股$', s)
            if m:
                return float(m.group(1)) * 10000
            # 处理"亿"
            m = re.match(r'^(-?[\d.]+)亿$', s)
            if m:
                return float(m.group(1)) * 100000000
            # 处理"万元"
            m = re.match(r'^(-?[\d.]+)万元$', s)
            if m:
                return float(m.group(1)) * 10000
            # 处理"元"
            m = re.match(r'^(-?[\d.]+)元$', s)
            if m:
                return float(m.group(1))
            # 纯数值
            m = re.match(r'^(-?[\d.]+)$', s)
            if m:
                return float(m.group(1))
            return s  # 无法解析则保留原值

        for col in ["volume", "amount", "pct_chg", "turnover_rate"]:
            if col in df.columns:
                df[col] = df[col].apply(_parse_chinese_number)

        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        if "date" in df.columns:
            df = df.sort_values("date", ascending=True).reset_index(drop=True)
        return df

    @staticmethod
    def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标 MA5/MA10/MA20/量比。"""
        df = df.copy()
        if "close" in df.columns:
            df["ma5"] = df["close"].rolling(window=5, min_periods=1).mean().round(2)
            df["ma10"] = df["close"].rolling(window=10, min_periods=1).mean().round(2)
            df["ma20"] = df["close"].rolling(window=20, min_periods=1).mean().round(2)
        if "volume" in df.columns:
            avg_vol = df["volume"].rolling(window=5, min_periods=1).mean()
            df["volume_ratio"] = (df["volume"] / avg_vol.shift(1)).fillna(1.0).round(2)
        return df

    def _parse_realtime_from_dto(self, dto_list: List[Any], stock_code: str) -> Optional[Any]:
        """从 DTO 列表解析实时行情数据，返回 UnifiedRealtimeQuote 兼容对象。"""
        try:
            from .realtime_types import UnifiedRealtimeQuote
        except ImportError:
            # 如果 realtime_types 不可用，返回简单字典对象
            return self._parse_realtime_as_dict(dto_list, stock_code)

        for dto in dto_list:
            if not isinstance(dto, dict):
                continue
            table = dto.get("table") or {}
            if not isinstance(table, dict):
                continue

            # 提取 headName 和 nameMap
            headers = table.get("headName") or []
            name_map = dto.get("nameMap") or {}

            # 提取指标值
            data_keys = [k for k in table.keys() if k != "headName"]
            if not data_keys or not isinstance(headers, list):
                continue

            # 尝试构建行情对象
            quote_data: Dict[str, Any] = {}
            for key in data_keys:
                values = table.get(key, [])
                if not isinstance(values, list):
                    values = [values]
                label = name_map.get(str(key)) or name_map.get(key) or str(key)
                if isinstance(label, (dict, list)):
                    label = _flatten_value(label)
                for i, h in enumerate(headers):
                    if i < len(values):
                        col_name = _flatten_value(h)
                        if label:
                            quote_data[f"{label}_{col_name}"] = values[i]
                        else:
                            quote_data[col_name] = values[i]

            # 尝试从 quote_data 构建 UnifiedRealtimeQuote
            try:
                quote = UnifiedRealtimeQuote(stock_code=stock_code)
                field_mapping = {
                    "最新价": "current_price",
                    "涨跌幅": "change_pct",
                    "涨跌额": "change",
                    "成交量": "volume",
                    "成交额": "amount",
                    "换手率": "turnover_rate",
                    "量比": "volume_ratio",
                    "市盈率": "pe_ratio",
                    "市净率": "pb_ratio",
                    "总市值": "market_cap",
                    "流通市值": "circulating_market_cap",
                    "今开": "open",
                    "最高": "high",
                    "最低": "low",
                    "昨收": "prev_close",
                }
                for cn_name, en_name in field_mapping.items():
                    for key, val in quote_data.items():
                        if cn_name in key:
                            try:
                                setattr(quote, en_name, float(val) if val else None)
                            except (ValueError, TypeError):
                                pass
                if hasattr(quote, "current_price") and quote.current_price:
                    quote.name = self._stock_name_cache.get(stock_code, "")
                    return quote
            except Exception as e:
                logger.debug(f"[MXFetcher] 构建 UnifiedRealtimeQuote 失败: {e}")

        return None

    def _parse_realtime_as_dict(self, dto_list: List[Any], stock_code: str) -> Optional[Dict]:
        """解析实时行情为字典（当 UnifiedRealtimeQuote 不可用时的兜底）。"""
        for dto in dto_list:
            if not isinstance(dto, dict):
                continue
            df = _dto_table_to_dataframe(dto)
            if df is not None and not df.empty:
                row = df.iloc[0].to_dict()
                row["stock_code"] = stock_code
                return row
        return None

    def _parse_chip_from_dto(self, dto_list: List[Any], stock_code: str) -> Optional[Any]:
        """从 DTO 解析筹码分布。"""
        try:
            from .base import ChipDistribution

            for dto in dto_list:
                if not isinstance(dto, dict):
                    continue
                df = _dto_table_to_dataframe(dto)
                if df is not None and not df.empty:
                    # 尝试解析为 ChipDistribution
                    chip = ChipDistribution(stock_code=stock_code)
                    # 填充数据
                    if "获利比例" in df.columns:
                        chip.profit_ratio = df["获利比例"].tolist()
                    if "筹码集中度" in df.columns:
                        chip.concentration = df["筹码集中度"].tolist()
                    return chip
        except Exception:
            pass

        # 无法解析为 ChipDistribution，返回 None
        return None


# === 异常类（与 base.py 兼容）===
class DataFetchError(Exception):
    """数据获取异常"""
    pass
