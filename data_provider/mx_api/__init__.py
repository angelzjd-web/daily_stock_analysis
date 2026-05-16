# -*- coding: utf-8 -*-
"""
===================================
东方财富妙想 API 数据源模块
===================================

基于东方财富妙想大模型 API，提供：
1. mx_finance_data - 金融数据查询（行情、基本面、资金流向等）
2. mx_finance_search - 金融资讯搜索（新闻、研报、公告等）
3. mx_macro_data - 宏观经济数据查询
4. mx_stocks_screener - 选股/选板块/选基金筛选
5. earnings_review - 业绩点评

所有 API 共享：
- API Key: EM_API_KEY
- Base URL: https://ai-saas.eastmoney.com
- 请求方式: POST JSON + em_api_key header
"""

from .finance_data import query_mx_finance_data, query_mx_finance_data_direct
from .finance_search import query_financial_news
from .macro_data import query_mx_macro_data
from .stocks_screener import query_mx_stocks_screener

__all__ = [
    "query_mx_finance_data",
    "query_mx_finance_data_direct",
    "query_financial_news",
    "query_mx_macro_data",
    "query_mx_stocks_screener",
]
