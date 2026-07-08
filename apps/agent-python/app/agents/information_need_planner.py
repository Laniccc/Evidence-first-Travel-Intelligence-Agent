from app.schemas.information_need import InformationNeed, InformationNeedType, NeedPriority
from app.schemas.travel_task import TravelTask, TravelTaskType


class InformationNeedPlanner:
    @classmethod
    def plan(cls, task: TravelTask) -> list[InformationNeed]:
        place = task.places[0].canonical_name if task.places else None
        city = task.city
        date = task.travel_date
        needs: list[InformationNeed] = []

        def add(need_type: InformationNeedType, priority: NeedPriority, reason: str, *, fallback: bool = True) -> None:
            needs.append(
                InformationNeed(
                    need_type=need_type,
                    priority=priority,
                    place=place,
                    city=city,
                    date=date,
                    reason=reason,
                    acceptable_staleness="recent" if need_type != InformationNeedType.WEATHER else "live",
                    fallback_allowed=fallback,
                )
            )

        if task.task_type == TravelTaskType.CROWD_INQUIRY:
            add(InformationNeedType.CROWD_LEVEL, NeedPriority.HIGH, "用户询问人流/拥挤程度")
            add(InformationNeedType.QUEUE_TIME, NeedPriority.MEDIUM, "排队时间与拥挤相关")
            add(InformationNeedType.EVENT, NeedPriority.MEDIUM, "活动/节假日可能影响人流", fallback=True)
            add(InformationNeedType.WEATHER, NeedPriority.LOW, "天气间接影响出行人流", fallback=True)
            if "今天" in task.rewritten_query or task.travel_date:
                add(InformationNeedType.RESERVATION_POLICY, NeedPriority.MEDIUM, "预约政策影响入场人流")
            return needs

        if task.task_type == TravelTaskType.SINGLE_PLACE_SUITABILITY or "elderly_suitability" in task.key_concerns:
            add(InformationNeedType.WALKING_INTENSITY, NeedPriority.HIGH, "长辈游览需评估步行强度")
            add(InformationNeedType.ACCESSIBILITY, NeedPriority.HIGH, "无障碍与休息可达性")
            add(InformationNeedType.CROWD_LEVEL, NeedPriority.HIGH, "拥挤程度影响体验")
            add(InformationNeedType.TRANSIT, NeedPriority.HIGH, "公共交通便利性")
            add(InformationNeedType.NEARBY_REST_AREA, NeedPriority.MEDIUM, "途中休息点")
            add(InformationNeedType.OPENING_HOURS, NeedPriority.MEDIUM, "开放时间安排")
            add(InformationNeedType.WEATHER, NeedPriority.MEDIUM, "天气对体力影响")
            if "stroller_friendliness" in task.key_concerns:
                add(InformationNeedType.STROLLER_FRIENDLINESS, NeedPriority.HIGH, "婴儿车/推车友好性")
            return needs

        if task.task_type == TravelTaskType.COMPARE_PLACES:
            for nt in [InformationNeedType.CROWD_LEVEL, InformationNeedType.WALKING_INTENSITY, InformationNeedType.TRANSIT]:
                add(nt, NeedPriority.HIGH, f"多景点比较：{nt.value}")
            add(InformationNeedType.OPENING_HOURS, NeedPriority.MEDIUM, "开放时间")
            return needs

        if task.task_type == TravelTaskType.ITINERARY_PLANNING:
            add(InformationNeedType.TRANSIT, NeedPriority.REQUIRED, "行程交通串联")
            add(InformationNeedType.OPENING_HOURS, NeedPriority.HIGH, "景点开放时间")
            add(InformationNeedType.NEARBY_FOOD, NeedPriority.MEDIUM, "途中餐饮")
            add(InformationNeedType.WEATHER, NeedPriority.MEDIUM, "天气风险")
            return needs

        if task.task_type == TravelTaskType.WEATHER_RISK:
            add(InformationNeedType.WEATHER, NeedPriority.REQUIRED, "天气风险评估")
            add(InformationNeedType.CROWD_LEVEL, NeedPriority.LOW, "天气影响人流")
            return needs

        if task.task_type == TravelTaskType.FOOD_NEARBY:
            add(InformationNeedType.NEARBY_FOOD, NeedPriority.REQUIRED, "附近餐饮")
            add(InformationNeedType.NEARBY_REST_AREA, NeedPriority.MEDIUM, "休息点")
            return needs

        if task.task_type == TravelTaskType.LODGING_AREA:
            add(InformationNeedType.LOCKER, NeedPriority.LOW, "行李寄存参考")
            return needs

        if task.task_type == TravelTaskType.TRANSPORT_PLANNING:
            add(InformationNeedType.TRANSIT, NeedPriority.REQUIRED, "交通规划")
            return needs

        # place_fact_lookup / open_ended
        if place:
            add(InformationNeedType.OPENING_HOURS, NeedPriority.HIGH, "基础景点信息")
            add(InformationNeedType.TICKET_PRICE, NeedPriority.MEDIUM, "票价信息")
        else:
            add(InformationNeedType.FALLBACK_WEB_LOOKUP, NeedPriority.HIGH, "城市/区域游览与景点建议")
            add(InformationNeedType.EVENT, NeedPriority.MEDIUM, "当地活动与季节亮点", fallback=True)
        add(InformationNeedType.TRANSIT, NeedPriority.MEDIUM, "交通信息")
        return needs
