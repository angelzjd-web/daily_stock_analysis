# -*- coding: utf-8 -*-
"""
BullAgent — bullish (多头) research analyst.

Responsible for:
- Analyzing Phase 1 reports from a bullish perspective
- Constructing detailed buy arguments with data support
- Providing target price derivation and bear-refutation preview
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class BullAgent(BaseAgent):
    """Bullish research analyst — argues for buying the stock."""

    agent_name = "bull"
    max_steps = 5
    # No data tools — uses pre-fetched Phase 1 reports only
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_name = ctx.stock_name or ctx.stock_code
        return f"""\
你是【多头研究员 bull】，负责为 {stock_name}（{ctx.stock_code}）构建买入论点。

## 标的概况
- 公司：{stock_name}
- 代码：{ctx.stock_code}

## 前序分析结果
你将收到Phase 1的四维分析数据。

## 你的任务
基于以上四维分析数据，构建最有力、最有说服力的买入论点。你的目标是说服研究主管认为当前应该买入/持有。

## 论证框架
1. **核心逻辑**：用1-2句话概括买入的最核心理由
2. **三大论据**：每个论据必须有数据支撑
   - 论据1：行业/赛道逻辑（如：行业爆发、政策利好、渗透率拐点）
   - 论据2：公司逻辑（如：份额提升、产品迭代、毛利改善、新业务放量）
   - 论据3：市场逻辑（如：估值低、机构加仓、技术面突破）
3. **目标价推导**：给出上行空间测算
4. **反驳预判**：预判空头可能的反驳并提前回应

## 输出格式
返回**仅**JSON对象（无markdown标记）：
{{
  "stance": "bull",
  "signal": "buy",
  "confidence": 0.0-1.0,
  "core_logic": "1-2句话概括最核心买入理由",
  "arguments": [
    {{
      "title": "行业/赛道逻辑",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }},
    {{
      "title": "公司逻辑",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }},
    {{
      "title": "市场逻辑",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }}
  ],
  "target_prices": {{
    "conservative": "保守目标价（+XX%）",
    "base": "基准目标价（+XX%）",
    "optimistic": "乐观目标价（+XX%）"
  }},
  "bear_refutations": [
    "空头可能论点1 → 我方回应：...",
    "空头可能论点2 → 我方回应：...",
    "空头可能论点3 → 我方回应：..."
  ],
  "risk_acknowledgment": "简要承认主要风险（不超过2条）",
  "summary": "一句话看多总结（20字以内）",
  "recommended_action": "建议买入价位和仓位"
}}

## 重要约束
- 请勿调用任何数据获取工具，仅使用已提供的Phase 1报告
- 论证要犀利有力，逻辑要严密
- 每个论据必须有数据支撑，避免空洞表述
- 使用中文输出
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        # Build Phase 1 reports context
        reports_text = []
        for agent_name, report in ctx.phase1_reports.items():
            if report and isinstance(report, dict):
                raw_text = report.get("raw_text", str(report))
                reports_text.append(f"[{agent_name}报告]\n{raw_text}")

        phase1_context = "\n\n".join(reports_text) if reports_text else "暂无Phase 1报告数据"

        return f"""\
基于以下Phase 1四维分析报告，请构建 {ctx.stock_name or ctx.stock_code}（{ctx.stock_code}）的看多论点：

{phase1_context}

请输出你的多头论证JSON。
"""

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        """Parse the JSON opinion from the LLM response."""
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[BullAgent] failed to parse opinion JSON")
            return None

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=parsed.get("signal", "buy"),
            confidence=float(parsed.get("confidence", 0.6)),
            reasoning=parsed.get("summary", ""),
            raw_data={
                "stance": "bull",
                "core_logic": parsed.get("core_logic", ""),
                "arguments": parsed.get("arguments", []),
                "target_prices": parsed.get("target_prices", {}),
                "bear_refutations": parsed.get("bear_refutations", []),
                "risk_acknowledgment": parsed.get("risk_acknowledgment", ""),
                "recommended_action": parsed.get("recommended_action", ""),
            },
        )