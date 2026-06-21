from app.agents.normalized_request_to_semantic_frame import NormalizedRequestToSemanticFrame
from app.agents.normalized_request_to_travel_task import NormalizedRequestToTravelTask
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.travel_task import TravelTask


class NormalizedRequestToQueryUnderstanding:
    @classmethod
    def convert(
        cls,
        req: NormalizedUserRequest,
        frame: SemanticFrame | None = None,
        task: TravelTask | None = None,
    ) -> QueryUnderstandingResult:
        frame = frame or NormalizedRequestToSemanticFrame.convert(req)
        task = task or NormalizedRequestToTravelTask.convert(req)

        resolved: dict[str, str] = {}
        for entity in req.entities:
            if entity.source == "conversation_context":
                resolved["here"] = entity.normalized_name or entity.text
                resolved["place"] = entity.normalized_name or entity.text

        return QueryUnderstandingResult(
            rewritten_query=req.rewritten_query,
            semantic_frame=frame,
            travel_task=task,
            resolved_references=resolved,
            missing_critical_info=list(req.missing_critical_info),
            needs_clarification=req.needs_clarification,
            clarification_question=req.clarification_question,
            assumptions=[],
            confidence=req.confidence,
            key_concerns=[n.need_type for n in req.information_needs],
        )
