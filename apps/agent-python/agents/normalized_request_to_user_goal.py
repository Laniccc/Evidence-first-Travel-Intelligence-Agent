from app.agents.travel_task_to_user_goal_adapter import TravelTaskToUserGoalAdapter
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.travel_task import TravelTask
from app.schemas.user_query import UserContext, UserGoal


class NormalizedRequestToUserGoal:
    @classmethod
    def convert(
        cls,
        req: NormalizedUserRequest,
        task: TravelTask,
        user_ctx: UserContext | None = None,
    ) -> UserGoal:
        return TravelTaskToUserGoalAdapter.to_user_goal(task, user_ctx)
