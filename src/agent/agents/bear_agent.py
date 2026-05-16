# -*- coding: utf-8 -*-
"""
BearAgent — bearish (空头) research analyst.

Responsible for:
- Analyzing Phase 1 reports from a bearish perspective
- Constructing detailed sell/avoid arguments with data support
- Providing downside risk assessment and bull-refutation preview
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class BearAgent(BaseAgent):
    """Bearish research analyst — argues against buying the stock."""

    agent_name = "bear"
    max_steps = 5
    # No data tools — uses pre-fetched Phase 1 reports only
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_name = ctx.stock_name or ctx.stock_code
        return f"""\
你是【空头研究员 bear】，负责为 {stock_name}（{ctx.stock_code}）构建看空论点。

## 标的概况
- 公司：{stock_name}
- 代码：{ctx.stock_code}

## 前序分析结果
你将收到Phase 1的四维分析数据。

## 你的任务
基于以上四维分析数据，构建最有力、最有说服力的看空论点。你的目标是说服研究主管认为当前应该卖出/规避。

## 论证框架
1. **核心逻辑**：用1-2句话概括看空的最核心理由
2. **三大论据**：每个论据必须有数据支撑
   - 论据1：行业/赛道风险（如：行业衰退、政策打压、渗透率见顶）
   - 论据2：公司风险（如：份额流失、产品老化、毛利恶化、新业务不及预期）
   - 论据3：市场风险（如：估值过高、机构减持、技术面破位）
3. **下行空间测算**：给出最大跌幅估算
4. **多头反驳预判**：预判多头可能的反驳并提前回应

## 输出格式
返回**仅**JSON对象（无markdown标记）：
{{
  "stance": "bear",
  "signal": "sell",
  "confidence": 0.0-1.0,
  "core_logic": "1-2句话概括最核心看空理由",
  "arguments": [
    {{
      "title": "行业/赛道风险",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }},
    {{
      "title": "公司风险",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }},
    {{
      "title": "市场风险",
      "detail": "详细论证（100字以上，含数据点）",
      "data_points": ["数据点1", "数据点2"]
    }}
  ],
  "downside_targets": {{
    "moderate": "中度下行目标价（-XX%）",
    "severe": "严重下行目标价（-XX%）"
  }},
  "bull_refutations": [
    "多头可能论点1 → 我方回应：...",
    "多头可能论点2 → 我方回应：...",
    "多头可能论点3 → 我方回应：..."
  ],
  "opportunity_acknowledgment": "简要承认潜在机会（不超过2条）",
  "summary": "一句话看空总结（20字以内）",
  "recommended_action": "建议规避或减仓策略"
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
基于以下Phase 1四维分析报告，请构建 {ctx.stock_name or ctx.stock_code}（{ctx.stock_code}）的看空论点：

{phase1_context}

请输出你的空头论证JSON。
"""

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        """Parse the JSON opinion from the LLM response."""
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[BearAgent] failed to parse opinion JSON")
            return None

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=parsed.get("signal", "sell"),
            confidence=float(parsed.get("confidence", 0.6)),
            reasoning=parsed.get("summary", ""),
            raw_data={
                "stance": "bear",
                "core_logic": parsed.get("core_logic", ""),
                "arguments": parsed.get("arguments", []),
                "downside_targets": parsed.get("downside_targets", {}),
                "bull_refutations": parsed.get("bull_refutations", []),
                "opportunity_acknowledgment": parsed.get("opportunity_acknowledgment", ""),
                "recommended_action": parsed.get("recommended_action", ""),
            },
        )