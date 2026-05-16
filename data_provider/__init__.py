# -*- coding: utf-8 -*-
"""
===================================
数据源策略层 - 包初始化
===================================

本包实现策略模式管理数据源，当前使用东方财富妙想 API (MXFetcher) 作为唯一数据源。

数据源：
- MXFetcher (Priority 0) - 东方财富妙想 API，覆盖 A股/港股/美股/基金/债券/宏观

原有数据源（akshare/tushare/baostock/efinance/pytdx/yfinance/longbridge）已作为兜底保留，
MXFetcher 不可用时自动降级到原有逻辑。

提示：优先级数字越小越优先
"""

from .base import BaseFetcher, DataFetcherManager
from .mx_fetcher import MXFetcher
from .efinance_fetcher import EfinanceFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .tushare_fetcher import TushareFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher
from .longbridge_fetcher import LongbridgeFetcher
from .us_index_mapping import is_us_index_code, is_us_stock_code, get_us_index_yf_symbol, US_INDEX_MAPPING

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'MXFetcher',
    'EfinanceFetcher',
    'AkshareFetcher',
    'TushareFetcher',
    'PytdxFetcher',
    'BaostockFetcher',
    'YfinanceFetcher',
    'LongbridgeFetcher',
    'is_us_index_code',
    'is_us_stock_code',
    'is_hk_stock_code',
    'get_us_index_yf_symbol',
    'US_INDEX_MAPPING',
]
