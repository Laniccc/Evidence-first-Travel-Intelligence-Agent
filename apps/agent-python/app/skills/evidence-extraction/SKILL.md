---
name: evidence-extraction
description: Extract factual claims from web page content using structured extraction patterns.
triggers: extract,claim,fetch,evidence,抓取,提取,声明,事实
---

# Evidence Extraction Skill

Use this skill when reading web page content to extract claims for research synthesis.

## Workflow

1. Read the fetched page content and identify the main topic.
2. Extract 3-5 specific, verifiable claims. Each claim must:
   - Be a concrete statement of fact, data point, or analysis
   - Be directly traceable to a sentence in the source
   - Include numerical data when available (statistics, dates, counts)
3. Classify each claim by type: `fact`, `statistical_claim`, `analysis`, `opinion`, `summary`.
4. Assign confidence to each claim:
   - `high`: Directly stated with specific numbers or citations
   - `medium`: Reasonably inferred from the text
   - `low`: Indirect or ambiguous
5. Distinguish the author's claims from your own inference.
6. If the page content is incomplete, noisy, or auto-generated, say so and reduce confidence.

## Extraction Rules

- DO extract: specific numbers, named entities, method descriptions, comparison results, official statements.
- DO NOT extract: generic marketing language, navigation text, ads, boilerplate.
- When a page contains a list or ranking (e.g., GitHub trending repos), extract the list items with their attributes.
- For Chinese sources, extract both the original Chinese claim and provide an English summary.

## Output Format

```json
{
  "claims": [
    {"claim": "Specific factual statement", "type": "fact|statistical_claim|analysis|opinion|summary", "confidence": "high|medium|low"}
  ]
}
```

## Post-Extraction Check

After extraction, verify:
- Are there at least 3 claims?
- Do claims reference specific data from the source?
- Are claims distinguishable from background knowledge?
- If no useful claims were found, report "no_extractable_claims" rather than fabricating.
