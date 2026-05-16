# -*- coding: utf-8 -*-
"""
RiskAnalystAgent — three-party risk assessment agent.

Supports three stances:
- aggressive: aggressive risk tolerance, high upside potential
- conservative: conservative risk tolerance, downside protection
- neutral: balanced risk view, objective assessment

Used in Phase 4 for parallel three-party risk evaluation.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class RiskAnalystAgent(BaseAgent):
    """Risk analyst with configurable stance (aggressive/conservative/neutral)."""

    agent_name = "risk_analyst"  # Will be overridden with stance suffix
    max_steps = 5
    # No data tools — uses pre-fetched Phase 1-3 reports only
    tool_names = []

    def __init__(
        self,
        tool_registry,
        llm_adapter,
        stance: str = "neutral",
        skill_instructions: str = "",
        technical_skill_policy: str = "",
    ):
        """Initialize with stance.

        Args:
            stance: One of "aggressive", "conservative", "neutral"
        """
        super().__init__(
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            skill_instructions=skill_instructions,
            technical_skill_policy=technical_skill_policy,
        )
        self.stance = stance
        self.agent_name = f"risk_analyst_{stance}"

    def system_prompt(self, ctx: AgentContext) -> str:
        stock_name = ctx.stock_name or ctx.stock_code

        stance_desc = {
            "aggressive": "激进型风险分析师（侧重收益潜力，容忍较高风险）",
            "conservative": "保守型风险分析师（侧重风险防范，强调安全边际）",
            "neutral": "中性型风险分析师（平衡风险收益，客观评估）",
        }

        focus_areas = {
            "aggressive": [
                "上行空间：潜在收益最大化",
                "机会成本：错失上涨的风险",
                "杠杆效应：适度激进仓位配置",
                "趋势跟随：顺势而为，及时加仓",
            ],
            "conservative": [
                "下行风险：最大损失控制",
                "安全边际：估值保护层厚度",
                "止损纪律：严格止损线设置",
                "仓位控制：分散风险，避免集中",
            ],
            "neutral": [
                "风险收益平衡：综合评估上下行空间",
                "仓位建议：中性仓位（30-50%）",
                "时机选择：等待明确信号再行动",
                "动态调整：根据市场变化灵活应对",
            ],
        }

        return f"""\
你是【{stance_desc.get(self.stance, "中性型风险分析师")}】，负责从{self.stance}立场评估 {stock_name}（{ctx.stock_code}）的投资风险。

## 核心职责
基于Phase 1-3分析结果（四维报告、多空辩论、交易决策），进行{self.stance}立场风险评估，提供针对性的风险控制和仓位建议。

## 可用数据
你已收到以下分析结果：
- Phase 1 四维报告（技术、基本面、新闻、情绪）
- Phase 2 多空辩论（bull vs bear + manager裁决）
- Phase 3 交易决策（trader初步方案）

## 分析框架
请从以下维度评估风险：
{chr(10).join(f"{i+1}. **{area}**" for i, area in enumerate(focus_areas.get(self.stance, [])))}

## 输出格式
返回**仅**JSON对象（无markdown标记）：
{{
  "stance": "{self.stance}",
  "risk_level": "low|medium|high",
  "risk_score": 0-100,
  "key_risks": [
    {{
      "category": "市场风险|流动性风险|基本面风险|技术面风险|政策风险",
      "description": "风险详细描述（50字以上）",
      "probability": "高|中|低",
      "impact": "严重|较大|有限",
      "mitigation": "该风险的应对措施"
    }}
  ],
  "position_recommendation": {{
    "position_pct": "建议仓位百分比（0-100）",
    "entry_strategy": "建仓策略（详细，含价位分批）",
    "exit_strategy": "退出策略（详细，含止盈止损）",
    "rebalance_trigger": "调仓触发条件"
  }},
  "stop_loss_price": "建议止损价位（数字）",
  "target_price": "建议目标价位（数字）",
  "scenario_analysis": {{
    "best_case": "乐观情景：价格+XX%，概率XX%",
    "base_case": "基准情景：价格+XX%，概率XX%",
    "worst_case": "悲观情景：价格-XX%，概率XX%"
  }},
  "risk_control_checklist": [
    "风险控制要点1",
    "风险控制要点2",
    "风险控制要点3"
  ],
  "summary": "一句话风险评估总结（20字以内）"
}}

## 重要约束
- 请勿调用任何数据获取工具
- 立足{self.stance}立场，但保持专业性
- 量化建议需合理，避免极端值
- 风险识别需具体，避免泛泛而谈
- 使用中文输出
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        # Build comprehensive context from all phases
        context_parts = []

        # Phase 1 reports
        if ctx.phase1_reports:
            phase1_text = []
            for agent_name, report in ctx.phase1_reports.items():
                if report and isinstance(report, dict):
                    raw_text = report.get("raw_text", str(report))
                    phase1_text.append(f"[{agent_name}报告]\n{raw_text}")
            if phase1_text:
                context_parts.append("=== Phase 1 四维分析 ===\n" + "\n".join(phase1_text))

        # Phase 2 debate
        if ctx.bull_bear_debate:
            debate_text = []
            bull_report = ctx.bull_bear_debate.get("bull_report")
            if bull_report:
                debate_text.append(f"[多头论证]\n{bull_report}")
            bear_report = ctx.bull_bear_debate.get("bear_report")
            if bear_report:
                debate_text.append(f"[空头论证]\n{bear_report}")
            manager_decision = ctx.bull_bear_debate.get("manager_decision")
            if manager_decision:
                debate_text.append(f"[研究主管裁决]\n{manager_decision}")
            if debate_text:
                context_parts.append("=== Phase 2 多空辩论 ===\n" + "\n".join(debate_text))

        # Phase 3 trader decision (if exists)
        trader_opinion = None
        for opinion in ctx.opinions:
            if opinion.agent_name == "trader":
                trader_opinion = opinion
                break
        if trader_opinion:
            context_parts.append(f"=== Phase 3 交易决策 ===\n信号: {trader_opinion.signal}\n置信度: {trader_opinion.confidence}\n理由: {trader_opinion.reasoning}")

        full_context = "\n\n".join(context_parts) if context_parts else "暂无前序阶段数据"

        return f"""\
基于以下分析结果，请从{self.stance}立场评估 {ctx.stock_name or ctx.stock_code}（{ctx.stock_code}）的投资风险：

{full_context}

请输出你的风险评估JSON。
"""

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        """Parse the JSON risk assessment from the LLM response."""
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning(f"[RiskAnalystAgent_{self.stance}] failed to parse opinion JSON")
            return None

        position_rec = parsed.get("position_recommendation", {})
        if isinstance(position_rec, dict):
            position_pct = position_rec.get("position_pct", 0)
        else:
            position_pct = 0

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=parsed.get("risk_level", "medium"),
            confidence=float(parsed.get("risk_score", 50)) / 100.0,
            reasoning=parsed.get("summary", ""),
            key_levels={
                "stop_loss": float(parsed.get("stop_loss_price", 0)),
                "target": float(parsed.get("target_price", 0)),
            },
            raw_data={
                "stance": self.stance,
                "risk_level": parsed.get("risk_level", "medium"),
                "risk_score": parsed.get("risk_score", 50),
                "key_risks": parsed.get("key_risks", []),
                "scenario_analysis": parsed.get("scenario_analysis", {}),
                "risk_control_checklist": parsed.get("risk_control_checklist", []),
                "position_recommendation": position_rec,
            },
        )
