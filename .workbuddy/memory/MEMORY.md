# 工作记忆

## 项目概况
- 项目：A股自选股智能分析系统 (DSA)
- 技术栈：FastAPI + SQLAlchemy + React (Vite)
- 数据库：SQLite (开发)

## 多用户认证系统 (2026-05-15 完成)
- 从单密码认证升级到多用户注册/登录系统
- 后端模块：`src/auth.py`（User模型、UserService、session管理）
- API端点：`api/v1/endpoints/auth.py`（login/register/logout/change-password/users管理）
- 认证中间件：`api/middlewares/auth.py`（Cookie session + request.state.user_id/user_role）
- 依赖注入：`api/deps.py`（get_current_user_id/get_current_user_role）
- 数据隔离：history/analysis端点已实现user_id过滤，storage层已支持user_id参数
- 前端：AuthContext + LoginPage + UserManagementCard + AdminRoute

### 数据隔离实现路径
- **全部完成（25/25 端点已隔离）**：
  - history端点（列表/详情/删除/新闻/Markdown）
  - analysis端点（同步/异步分析→Pipeline→save_analysis_history）
  - agent聊天会话（sessions/messages/delete 全链路 user_id 隔离，含 executor→conversation→storage + orchestrator）
  - analysis任务列表（tasks/stream/status 按 user_id 过滤，TaskInfo 新增 user_id 字段）
  - portfolio模块（全部 16 端点通过 owner_id 隔离，服务层 13 方法加 owner_id 参数）
  - backtest模块（4 端点：run/results/performance/performance/{code}，repo 层通过 AnalysisHistory.user_id 子查询过滤）
  - usage模块（1 端点：summary，LLMUsage.user_id 直接过滤）
- 关键调用链5：backtest.py → get_current_user_id(http_request) → BacktestService(user_id=) → BacktestRepo._build_result_conditions(user_id=) → 子查询 AnalysisHistory.id WHERE user_id=
- 关键调用链6：usage.py → get_current_user_id(http_request) → db_manager.get_llm_usage_summary(user_id=) → LLMUsage.user_id == user_id
- 关键调用链：analysis.py → AnalysisService.analyze_stock(db_user_id=) → StockAnalysisPipeline(db_user_id=) → save_analysis_history(user_id=)
- 关键调用链2：history.py → HistoryService.get_history_list(user_id=) → get_analysis_history_paginated(user_id=)
- 关键调用链3：agent.py → executor.chat(user_id=db_user_id) → conversation_manager.add_message(user_id=) → save_conversation_message(user_id=)
- 关键调用链3b：orchestrator.chat(user_id=) → 同上（multi 模式下也隔离）
- 关键调用链4：portfolio.py → _get_owner_id(http_request) → str(db_user_id) 作为 owner_id
- **前端隔离**：AuthContext 检测 currentUser.id 变化时调用 agentChatStore.resetStore()，清除 sessions/messages/localStorage

### 环境配置
- `.env` 中 `ADMIN_AUTH_ENABLED=true` 启用认证
- 首次启动自动创建默认admin用户（用户名admin，密码admin）
- 首次登录admin时需提供passwordConfirm字段设置初始密码

### 测试结果
- 管理员登录/注册/登出：✅
- 用户CRUD（管理员创建/修改角色/禁用/重置密码/删除）：✅
- 权限隔离（普通用户无法访问admin API）：✅
- 数据隔离（history按user_id过滤）：✅
- 未登录访问被401拒绝：✅
- 密码修改：✅
- 禁用用户无法登录：✅
- 前端构建：✅

## 积分系统 (2026-05-16 完成)
- 普通分析扣 5 积分，Agent 对话扣 20 积分
- 所有账户默认 0 积分，积分不足阻断操作（余额 < 消耗额则拒绝，返回 402）
- 管理员可在后台修改每个账户积分
- 后端模块：`src/points.py`（积分服务，含 `check_points_sufficient` 预检查）、`src/storage.py`（PointTransaction模型）
- API端点：`POST /auth/users/{id}/points`（管理员设置积分）、`GET /points/balance`（查余额）、`GET /points/transactions`（查变动记录）
- 前端：SidebarNav显示积分余额、UserManagementCard增加积分列和修改按钮、分析和聊天前本地预检查积分
- 关键决策：管理员也扣积分、积分不足阻断操作（402 insufficient_points）、认证关闭时不扣积分
- agent端点修复：agent_chat/agent_chat_stream 新增 Request 参数以获取 user_id
- 积分实时刷新：AuthContext.refreshPoints() + useDashboardLifecycle.onPointsChanged + ChatPage.handleSend后调refreshPoints

## 东方财富妙想 API 数据源 (2026-05-15 完成)
- 替换所有原有数据源（akshare/tushare/baostock/efinance/pytdx/yfinance/longbridge）为东方财富妙想API
- 核心适配器：`data_provider/mx_fetcher.py`（MXFetcher类，BaseFetcher兼容接口）
- API模块：`data_provider/mx_api/`（finance_data/finance_search/macro_data/stocks_screener/earnings_review）
- DataFetcherManager 默认只初始化 MXFetcher，原有 fetcher 作为回退保留
- SearchService 新增 MXFinanceSearchProvider（最高优先级，替代 Bocha/Tavily 等搜索源）
- 新API端点：`/api/v1/mx/finance-data|finance-search|macro-data|stocks-screener`
- 配置：`EM_API_KEY` 环境变量（默认值已内置）
- API Base: `https://ai-saas.eastmoney.com`，4个端点：searchData/searchNews/searchMacroData/selectSecurity
- 关键实现：宽格式→长格式K线转换（`_wide_dto_list_to_daily_dataframe`），中文数值单位解析
