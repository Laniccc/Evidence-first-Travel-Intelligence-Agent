---
name: verification
description: Verify research output against requirements, sources, evidence, and unsupported claims before delivery.
triggers: verify,check,evidence,citation,final,delivery,检查,证据,引用,校验,交付
---

# Verification Skill

Use this skill before final delivery or when reliability matters.

## Verification Workflow

1. **Requirements check**: Restate the user's original question. Does the report answer it?
2. **Claim-source mapping**: For each substantive claim in the report, verify there is a matching citation [N] with a real URL.
3. **Source accessibility**: Check that cited URLs are actual web pages that were fetched and read — not just search result links.
4. **Tier distribution**: Ensure core claims cite Tier 1-2 sources. Flag claims that rely solely on Tier 3-4 sources.
5. **Unsupported claims**: Identify statements that lack evidence. Mark them as assumptions or remove them.
6. **Cross-reference**: When multiple sources agree on a fact, note the corroboration. When one source is the sole support for an important claim, flag it as single-sourced.
7. **Gap report**: If the answer is incomplete, describe specifically what is missing and what kind of evidence would fill the gap.

## Delivery Decision

- **READY**: All requirements addressed, claims cited, sources verified.
- **DEGRADED**: Some claims lack citations or rely on low-tier sources — delivery OK but note in limitations.
- **INSUFFICIENT**: Core question unanswered or zero verifiable claims — should NOT deliver as complete. Return honest gap report.

## Output

- Requirements coverage (answered / partial / unanswered)
- Unsupported claims count
- Single-sourced claims count
- Tier distribution summary
- Delivery recommendation: ready | degraded | insufficient
