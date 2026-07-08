---
name: search-strategy
description: Plan and refine web search strategies with multiple search angles and source targeting.
triggers: search,query,find,discover,搜索,查询,查找,关键词
---

# Search Strategy Skill

Use this skill when planning how to find information on the web.

## Search Angle Framework

For any research topic, use these 6 angles to generate diverse search queries:

1. **Definition / Overview** — "What is X?" → `X definition`, `X overview guide`
2. **Data / Statistics** — "How many/much?" → `X statistics 2025`, `X trends data`
3. **Comparison / Analysis** — "X vs Y?" → `X vs Y comparison`, `X alternatives`
4. **Latest / Recent** — "What's new?" → `X latest developments 2025`, `X news`
5. **Examples / Cases** — "Show me real examples" → `X case studies`, `X examples`
6. **Official / Authoritative** — "From the source" → `site:docs.X.com`, `X documentation`

## Source Targeting

When a specific platform is the best data source, generate both search queries AND direct URLs:

| Data Need | Search Query | Direct URL |
|-----------|-------------|------------|
| GitHub trending | `site:github.com trending X` | `https://github.com/trending` |
| Wikipedia | `site:wikipedia.org X` | `https://en.wikipedia.org/wiki/X` |
| Academic papers | `site:arxiv.org X` | `https://arxiv.org/search/?query=X` |
| Official docs | `site:docs.X.com X` | Varies by technology |
| PyPI packages | `site:pypi.org X` | `https://pypi.org/search/?q=X` |

## Refinement Strategy

If the first round of evidence is insufficient:

1. Identify specific knowledge gaps.
2. Generate more targeted queries that fill those gaps — not just synonyms of the original query.
3. Try different search angles than round 1 (e.g., if round 1 was "overview", round 2 should be "data" or "examples").
4. If Chinese sources dominate and the topic needs English data, switch to English-only search terms.
5. If search results are noisy with unrelated content, add `site:` restrictions.

## Query Crafting Rules

- Keep search queries short: 2-7 words, keyword-style.
- Use specific technical terms, not vague phrases.
- For Chinese topics, include both Chinese and English queries.
- Avoid search terms that are too broad (single word) or too narrow (full sentences).
