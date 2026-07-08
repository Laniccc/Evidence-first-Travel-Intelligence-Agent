---
name: source-evaluation
description: Evaluate web source quality using a 5-tier rating system and classify trustworthiness.
triggers: source,quality,tier,verify,信源,质量,分级,可信度
---

# Source Evaluation Skill

Use this skill when gathering evidence from web searches or direct URLs.

## Source Tier System

| Tier | Rating | Examples | Behavior |
|------|--------|----------|----------|
| T1 | 0.90 | arxiv.org, *.gov, github.com, docs.python.org, wikipedia.org, stackoverflow.com | Prioritize adoption |
| T2 | 0.75 | medium.com, dev.to, freecodecamp.org, realpython.com, zhihu.com (high-quality) | Primary sources |
| T3 | 0.55 | Personal blogs, CSDN, juejin.cn, general web | Usable but not prioritized |
| T4 | 0.35 | Forums, unverified blogs, low-engagement posts | Needs cross-verification |
| T5 | 0.00 | Content farms, SEO spam, 17173.com, sohu.com | Discard immediately |

## Workflow

1. For each URL found, classify its domain into Tier 1-5.
2. For search engine redirect URLs (baidu.com/link, sogou.com/link), extract the real domain from the redirect target before classifying.
3. When the real domain can't be determined, use the page title as a hint: "GitHub Topics" → T1, "CSDN Blog" → T3.
4. Discard all Tier 5 sources immediately — they should never enter evidence or RAG.
5. Prefer Tier 1-2 sources for synthesis. Use Tier 3 only if higher-tier sources are unavailable.
6. Count the tier distribution: at least one Tier 1-2 source should be present for a quality report.

## Output

- Tier distribution summary
- Flagged Tier 5 sources (if any were caught)
- Recommendation: whether source quality is sufficient to proceed
