from app.policies.evidence_policy import EvidencePolicy
from app.schemas.semantic_frame import (
    AnswerMode,
    AnswerModeDecision,
    DecisionType,
    QueryScope,
    SemanticFrame,
    TimeScope,
)


class AnswerModeRouter:
  """Route by semantic intent + evidence policy — not by fixed question templates."""

  LIVE_FACT_NEEDS = frozenset(
      {
          "opening_hours",
          "ticket_price",
          "weather_today",
          "weather",
          "current_crowd",
          "reservation_policy",
      }
  )

  def route(
      self,
      frame: SemanticFrame,
      available_capabilities: set[str] | None = None,
  ) -> AnswerModeDecision:
      caps = available_capabilities or set()

      if frame.needs_clarification or self._needs_clarification(frame):
          return AnswerModeDecision(
              answer_mode=AnswerMode.CLARIFICATION_REQUIRED,
              reason="关键对象缺失或指代无法解析",
              limitations_to_add=["需要用户补充地点或时间等关键信息后才能继续。"],
          )

      if self._requires_exact_evidence(frame):
          tools = self._tools_for_needs(frame.information_needs, caps, required=True)
          return AnswerModeDecision(
              answer_mode=AnswerMode.EVIDENCE_REQUIRED,
              required_tools=tools,
              allow_knowledge_prior=False,
              reason="问题要求精确或实时事实，必须经工具获取 Evidence",
          )

      if frame.decision_type == DecisionType.BEST_TIME_TO_VISIT or "best_time_to_visit" in frame.information_needs:
          if frame.query_scope in {QueryScope.CITY, QueryScope.COUNTRY, QueryScope.REGION}:
              return AnswerModeDecision(
                  answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
                  optional_tools=self._tools_for_needs(["seasonality", "weather"], caps, required=False),
                  allow_knowledge_prior=True,
                  allow_partial_answer=True,
                  reason="目的地季节建议允许低置信度 model prior",
                  limitations_to_add=[
                      "这是基于一般季节规律的建议；具体年份天气、节庆日期、住宿价格需进一步查询。"
                  ],
              )

      if frame.can_answer_with_model_prior and frame.decision_type in {
          DecisionType.GENERAL_ADVICE,
          DecisionType.WHETHER_TO_GO,
          DecisionType.HOW_TO_CHOOSE,
      }:
          return AnswerModeDecision(
              answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
              optional_tools=self._tools_for_needs(frame.information_needs, caps, required=False),
              allow_knowledge_prior=True,
              allow_partial_answer=True,
              reason="稳定常识类建议，允许 KnowledgePriorTool",
          )

      if any(n in {"crowd_level", "current_crowd"} for n in frame.information_needs):
          return AnswerModeDecision(
              answer_mode=AnswerMode.ESTIMATION_ALLOWED,
              required_tools=self._tools_for_needs(["crowd_level"], caps, required=True) or ["reviews", "places"],
              optional_tools=["fallback"],
              allow_knowledge_prior=False,
              allow_partial_answer=True,
              reason="实时人流不可用，允许代理估算",
              limitations_to_add=["未接入实时人流，以下为评价与地图代理估算。"],
          )

      if frame.information_needs:
          tools = self._tools_for_needs(frame.information_needs, caps, required=False)
          if tools:
              return AnswerModeDecision(
                  answer_mode=AnswerMode.EVIDENCE_PREFERRED,
                  required_tools=tools,
                  optional_tools=["knowledge_prior"],
                  allow_knowledge_prior=frame.can_answer_with_model_prior,
                  allow_partial_answer=True,
                  reason="优先工具证据，失败可回退 model prior",
              )

      if frame.can_answer_with_model_prior:
          return AnswerModeDecision(
              answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
              allow_knowledge_prior=True,
              allow_partial_answer=True,
              reason="无强事实需求，允许 model prior",
          )

      return AnswerModeDecision(
          answer_mode=AnswerMode.UNSUPPORTED,
          reason="无法确定回答模式",
          limitations_to_add=["当前无法理解该问题类型，请补充更多细节。"],
      )

  def _needs_clarification(self, frame: SemanticFrame) -> bool:
      if "place_reference" in frame.missing_slots:
          return True
      if frame.query_scope == QueryScope.PLACE and not frame.entities.places:
          if frame.decision_type in {DecisionType.FACT_LOOKUP, DecisionType.RISK_CHECK}:
              return True
      return False

  def _requires_exact_evidence(self, frame: SemanticFrame) -> bool:
      if frame.requires_exact_fact or frame.requires_live_data:
          return True
      if frame.time_scope in {TimeScope.CURRENT, TimeScope.SPECIFIC_DATE} and any(
          n in self.LIVE_FACT_NEEDS for n in frame.information_needs
      ):
          return True
      for need in frame.information_needs:
          if need in self.LIVE_FACT_NEEDS:
              return True
          policy = EvidencePolicy.get(need)
          if policy.requires_exact_fact and frame.query_scope == QueryScope.PLACE:
              return True
      if frame.decision_type == DecisionType.FACT_LOOKUP:
          return any(EvidencePolicy.requires_evidence_for(n) for n in frame.information_needs)
      return False

  def _tools_for_needs(
      self,
      needs: list[str],
      caps: set[str],
      *,
      required: bool,
  ) -> list[str]:
      mapping = {
          "opening_hours": "official",
          "ticket_price": "official",
          "reservation_policy": "official",
          "weather": "weather",
          "weather_today": "weather",
          "crowd_level": "reviews",
          "current_crowd": "reviews",
          "transit": "transit",
          "seasonality": "weather",
          "best_time_to_visit": "weather",
          "nearby_food": "restaurant",
      }
      tools: list[str] = []
      for need in needs:
          tool = mapping.get(need)
          if tool and tool not in tools:
              if not caps or tool in caps or required:
                  tools.append(tool)
      return tools
