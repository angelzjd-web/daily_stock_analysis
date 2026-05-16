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
- **全部完成（所有端点已隔离）**：
  - history端点（列表/详情/删除/新闻/Markdown）
  - analysis端点（同步/异步分析→Pipeline→save_analysis_history；status端点DB回退也加了user_id过滤）
  - agent聊天会话（sessions/messages/delete 全链路 user_id 隔离，含 executor→conversation→storage + orchestrator）
  - analysis任务列表（tasks/stream/status 按 user_id 过滤，TaskInfo 新增 user_id 字段）
  - portfolio模块（全部 16 端点通过 owner_id 隔离，服务层 13 方法加 owner_id 参数）
  - backtest模块（4 端点：run/results/performance/performance/{code}，repo 层通过 AnalysisHistory.user_id 子查询过滤；BacktestSummary 按 user_id 隔离，唯一约束含 user_id）
  - usage模块（1 端点：summary，LLMUsage.user_id 直接过滤）
  - notification模块（3 端点：GET/PUT/DELETE，UserNotificationConfig.user_id 隔离）
  - agent/research（新增 user_id + 积分扣除 COST_RESEARCH=30）
  - agent/chat/send（新增认证校验）
  - mx数据模块（4 端点：finance-data/finance-search/macro-data/stocks-screener，积分扣除 COST_MX_DATA=2）
  - system_config模块（GET/PUT /config + test-channel + discover-models 加 _require_admin 校验）
  - conversation storage（get_conversation_history/conversation_session_exists 加 user_id 过滤）
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
- 普通分析扣 5 积分，Agent 对话扣 20 积分，深度研究扣 30 积分，妙想数据查询扣 2 积分
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

## 多智能体系统升级 - 5阶段工作流 (2026-05-16 完成)
- 参考`/Users/zhang/Desktop/trading-agent-team`项目的声明式Skill框架，增强现有FastAPI多Agent架构
- **新增Agent类**：
  - `src/agent/agents/bull_agent.py`：多头研究员（核心逻辑+三大论据+目标价推导+空头反驳预判）
  - `src/agent/agents/bear_agent.py`：空头研究员（核心逻辑+三大风险+下行空间测算+多头反驳预判）
  - `src/agent/agents/research_manager_agent.py`：研究主管（论证质量评估4维评分+核心分歧+风险收益比+验证点）
  - `src/agent/agents/risk_analyst_agent.py`：三方风险分析师（5类风险分类+情景分析3种+风险控制清单）
- **AgentContext扩展**（`src/agent/protocols.py`）：
  - `phase1_reports`: Phase 1四维分析报告（technical/fundamentals/news/sentiment）
  - `bull_bear_debate`: Phase 2多空辩论结果（bull_report/bear_report/manager_decision）
  - `risk_assessments`: Phase 4三方风险评估（aggressive/conservative/neutral）
- **orchestrator升级**（`src/agent/orchestrator.py`）：
  - 新增`_execute_parallel_agents`方法，使用ThreadPoolExecutor实现并行调度
  - 新增`_execute_phase_pipeline`方法，实现5阶段工作流：
    - Phase 1: 4个分析师并行（technical/fundamentals/news/sentiment）
    - Phase 2: 多空辩论顺序（bull → bear → manager）
    - Phase 3: 交易员决策（trader）
    - Phase 4: 3个风险分析师并行（aggressive/conservative/neutral）
    - Phase 5: 最终决策整合（decision）
  - VALID_MODES新增"phase"模式
  - 每个阶段/Agent都有详细中文进度事件（emoji标记+phase_label+agent_label）
- **config.py配置**：
  - `_VALID_ORCHESTRATOR_MODES`包含"phase"
  - 默认模式为"phase"（环境变量AGENT_ORCHESTRATOR_MODE默认"phase"）
- **前端适配**（`apps/dsa-web/src/pages/ChatPage.tsx`）：
  - 新增phase事件渲染逻辑（phase_start/phase_done/agent_completed/stage_start/stage_done）
  - loading状态新增实时phase进度面板（阶段标题块+Agent状态脉冲点）
  - getCurrentStage函数支持所有新事件类型
- **关键设计决策**：
  - Phase 1的fundamentals/sentiment暂时用IntelAgent占位（未来可扩展专用Agent）
  - 多空辩论Agent禁止数据工具调用，仅使用Phase 1报告（避免重复抓取）
  - 三方风险分析师同样禁止数据工具，依赖前序阶段结果
  - 并行执行最多5线程（ThreadPoolExecutor max_workers=5）
  - 进度事件包含phase标识和中文描述，前端按phase分组显示

### 关键Bug修复 (2026-05-16)
- **问题1**：日志检查发现系统一直在运行单智能体AgentExecutor，而非多智能体AgentOrchestrator
- **根源1**：`src/config.py`中`agent_arch`默认值为"single"，而`agent_orchestrator_mode`默认值为"phase"
- **修复1**：将`agent_arch`默认值改为"multi"（config.py:720）
- **问题2**：修复后发现orchestrator启动了，但mode是"standard"而非"phase"
- **根源2**：`src/agent/factory.py:341`的fallback默认值还是"standard"
- **修复2**：将factory.py的fallback默认值改为"phase"
- **验证点**：重启后日志应显示`Building AgentOrchestrator (mode=phase)` + ThreadPool + bull_agent等关键字
