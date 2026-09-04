"""Bounded catalog/fact vocabulary, never arbitrary model-generated FTS syntax."""

import re
from collections.abc import Sequence

from app.contracts.fact_type import FactType


_FACT_WORDS = {
    FactType.OPENING_HOURS: ("开放时间", "开放", "开馆", "闭馆", "时间", "hours"),
    FactType.TICKET_PRICE: ("门票", "票价", "价格", "ticket", "price"),
    FactType.RESERVATION: ("预约", "实名", "入馆", "reservation"),
    FactType.TRANSPORT: ("交通", "到达", "地址", "地铁", "transport"),
    FactType.ACCESSIBILITY: ("无障碍", "轮椅", "台阶", "步行", "accessibility"),
    FactType.VISITOR_NOTICE: ("须知", "提示", "公告", "游客", "notice"),
    FactType.GENERAL_DESCRIPTION: ("简介", "景点", "地址", "介绍", "description"),
}


class RetrievalQueryBuilder:
    MAX_TERMS = 32

    def from_entity_and_fact_types(self, entity: str, fact_types: Sequence[FactType],
                                   *, aliases: Sequence[str] = ()) -> str:
        values = [entity, *aliases[:4]]
        values.extend(word for fact in fact_types[:7] for word in _FACT_WORDS.get(fact, ()))
        terms = []
        for value in values:
            for term in re.findall(r"[\w\u3400-\u9fff]+", value[:200]):
                if term.casefold() in {"or", "and", "not", "near"} or term in terms:
                    continue
                terms.append(term)
                if len(terms) == self.MAX_TERMS:
                    return " ".join(terms)
        if not terms:
            raise ValueError("empty lexical query")
        return " ".join(terms)
