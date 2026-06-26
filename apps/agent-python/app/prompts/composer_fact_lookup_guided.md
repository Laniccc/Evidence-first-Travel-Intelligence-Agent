Answer style: fact_lookup_guided (S8, strict_fact_lookup task class).

The user asked a **hard fact** (ticket price, opening hours, reservation, elevation, etc.). Lead with the answer, not background.

## Structure (required)

1. **Headline conclusion**: State the fact directly in one sentence.
   - If evidence exists: e.g.「成人票 120 元（来源：…）」
   - If NOT in evidence: **「无法确认当前票价/开放时间」** — do not guess.
2. **Evidence bullets**: List EVERY item in `fact_lookup_presentation.fact_clues` with source_name and confidence.
   - Mark 官方 vs 第三方 when `official` flag is set.
   - If multiple prices exist, list all with sources; note conflict.
3. **Optional — place disambiguation**: If `disambiguation_presentation` exists, 2–3 lines at end only; do not block the answer.
4. **Limitations**: retrieval date, no official source, stale data risk.

## Rules

- Evidence-only: numbers and hours must come from `fact_clues` or `evidence_brief.curated_claims`.
- Do NOT invent 兵马俑/景区票价 from training data.
- Do NOT recommend restaurants, routes, or weather unless asked.
- Official source > ticket platform signal > general web search.

## Anti-patterns

- Burying the price under scenic history.
- Stating a specific CNY amount without a cited claim.
- Calling a blog post「官方」when source is not official.
