请解析以下旅行查询，输出 QueryUnderstandingResult JSON。

raw_user_query:
{{raw_user_query}}

conversation_context:
{{conversation_context}}

supported_regions:
{{supported_regions}}

entity_hints（LLM 语义地点提取结果，优先于固定 registry；仅用于识别 city/country/POI，不代表开放时间等事实）:
{{entity_hints}}

current_date:
{{current_date}}

只输出 JSON，不要其他文字。
