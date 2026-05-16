# -*- coding: utf-8 -*-
"""
ResearchManagerAgent — research manager (研究主管).

Responsible for:
- Arbitrating bull-bear debate with structured quality assessment
- Synthesizing both perspectives into balanced conclusion
- Making final investment recommendation before trader decision
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class ResearchManagerAgent(BaseAgent):
    """Research manager — arbitrates bull-bear debate and makes recommendation."""

    agent_name = "research_manager"
    max_steps = 5
    # No data tools — uses bull-bear debate results only
    tool_names = []

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_name = ctx.stock_name or ctx.stock_code
        return f"""\
你是【研究主管 research-manager】，负责裁决 {stock_name}（{ctx.stock_code}）的多空辩论。

## 标的概况
- 公司：{stock_name}
- 代码：{ctx.stock_code}

## 你的任务
作为研究主管，你需要客观、理性地裁决多空辩论。不能偏袒任何一方，必须基于数据和逻辑做出判断。

## 裁决框架
1. **论证质量评估**：评估多空双方的论证质量（数据充分性、逻辑严密性、论据独立性）
2. **核心分歧点**：识别多空最关键的分歧
3. **数据验证**：哪方的论据更经得起数据推敲
4. **催化剂权重**：考虑未来催化剂对多空论据的影响权重
5. **时间维度**：短期vs中长期，多空论据的时间有效性
6. **风险收益比**：基于多空目标价计算风险收益比

## 输出格式
返回**仅**JSON对象（无markdown标记）：
{{
  "final_signal": "buy|hold|sell",
  "confidence": 0.0-1.0,
  "stance_bias": "bull|bear|neutral",
  "quality_assessment": {{
    "data_sufficiency": {{"bull": "X/10", "bear": "X/10"}},
    "logic_rigor": {{"bull": "X/10", "bear": "X/10"}},
    "argument_independence": {{"bull": "X/10", "bear": "X/10"}}
  }},
  "core_disagreements": [
    "分歧1：我方判断 → 理由",
    "分歧2：我方判断 → 理由",
    "分歧3：我方判断 → 理由"
  ],
  "arbitration_reasoning": [
    "裁决依据1（100字以上，详细说明）",
    "裁决依据2（100字以上，详细说明）",
    "裁决依据3（100字以上，详细说明）"
  ],
  "risk_reward_ratio": {{
    "upside": "+XX%",
    "downside": "-XX%",
    "ratio": "1:X"
  }},
  "recommendation_for_trader": "给交易员的明确建议（仓位、价位、止损）",
  "key_verification_points": [
    "验证点1：时间窗口，验证方法...",
    "验证点2：时间窗口，验证方法..."
  ],
  "if_wrong": {{
    "wrong_signal": "判断错误的信号...",
    "stop_loss_condition": "止损条件..."
  }},
  "debate_summary": "多空辩论核心分歧总结（50字以内）"
}}

## 重要约束
- 请勿调用任何数据获取工具
- 裁决要客观、有担当、有逻辑
- 必须引用具体论点，避免泛泛而谈
- 使用中文输出
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        # Build bull-bear debate context
        debate_data = ctx.bull_bear_debate

        context_parts = []

        # Phase 1 reports summary
        if ctx.phase1_reports:
            phase1_text = []
            for agent_name, report in ctx.phase1_reports.items():
                if report and isinstance(report, dict):
                    raw_text = report.get("raw_text", str(report))
                    phase1_text.append(f"[{agent_name}报告]\n{raw_text}")
            if phase1_text:
                context_parts.append("=== 四维分析汇总 ===\n" + "\n".join(phase1_text))

        bull_report = debate_data.get("bull_report")
        if bull_report:
            context_parts.append(f"=== 多头论证 ===\n{bull_report}")

        bear_report = debate_data.get("bear_report")
        if bear_report:
            context_parts.append(f"=== 空头论证 ===\n{bear_report}")

        debate_context = "\n\n".join(context_parts) if context_parts else "暂无多空辩论数据"

        return f"""\
基于以下分析数据，请裁决 {ctx.stock_name or ctx.stock_code}（{ctx.stock_code}）的多空辩论：

{debate_context}

请输出你的研究主管裁决JSON。
"""

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        """Parse the JSON opinion from the LLM response."""
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[ResearchManagerAgent] failed to parse opinion JSON")
            return None

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=parsed.get("final_signal", "hold"),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=parsed.get("debate_summary", ""),
            raw_data={
                "stance_bias": parsed.get("stance_bias", "neutral"),
                "quality_assessment": parsed.get("quality_assessment", {}),
                "core_disagreements": parsed.get("core_disagreements", []),
                "arbitration_reasoning": parsed.get("arbitration_reasoning", []),
                "risk_reward_ratio": parsed.get("risk_reward_ratio", {}),
                "recommendation_for_trader": parsed.get("recommendation_for_trader", ""),
                "key_verification_points": parsed.get("key_verification_points", []),
                "if_wrong": parsed.get("if_wrong", {}),
            },
        )