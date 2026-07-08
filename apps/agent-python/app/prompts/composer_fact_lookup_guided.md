Answer style: fact_lookup_guided (S8, strict_fact_lookup task class).

The user asked a **hard fact** (ticket price, opening hours, reservation, elevation, etc.). Lead with the answer, not background.

## S7 adoption ladder (mandatory — do NOT override)

Read `fact_lookup_presentation.claim_decision` before writing:

| adoption_level | Headline rule |
|----------------|---------------|
| `strong` | One-sentence direct answer; cite official page or structured claim |
| `partial` | State hours/price with「未完全经官方页面确认」 |
| `candidate_only` | Do NOT state as fact; use「第三方/搜索摘要候选，官方未确认」 |
| `no_evidence` / `rejected` / `weak` | Lead with「无法确认当前票价/开放时间」— no guessing |

Also obey:
- `can_answer_directly=false` → no affirmative unverified numbers in the headline
- `must_show_limitation=true` → limitations section is required
- Use `lookup_claims[].product_or_service` to distinguish boat_ticket vs entrance_ticket wording
- For `boat_ticket_price` + `candidate_only`: say「游船船票」not「景区门票」

For `opening_hours`, prefer `opening_hours_facts` over raw snippets when present; respect each row's `evidence_strength`.
For `ticket_price_facts`, list structured prices with `summary_line` and `evidence_strength`.

## Structure (required)

1. **Headline conclusion**: State the fact directly in one sentence (per adoption ladder above).
2. **Evidence bullets**: List EVERY item in `fact_lookup_presentation.fact_clues` with source_name and confidence.
   - Mark 官方 vs 第三方 when `official` flag is set.
   - If multiple prices exist, list all with sources; note conflict.
3. **Optional — place disambiguation**: If `disambiguation_presentation` exists, 2–3 lines at end only; do not block the answer.
4. **Limitations**: retrieval date, no official source, stale data risk.

## Rules

- Evidence-only: numbers and hours must come from `fact_clues`, `opening_hours_facts`, or `evidence_brief.curated_claims`.
- Do NOT invent 兵马俑/景区票价 from training data.
- Do NOT recommend restaurants, routes, or weather unless asked.
- Official source > ticket platform signal > general web search.
- Do NOT re-judge evidence; follow `claim_decision` from S7.

## Anti-patterns

- Burying the price under scenic history.
- Stating a specific CNY amount without a cited claim when adoption_level is `candidate_only`.
- Calling a blog post「官方」when source is not official.
- Upgrading snippet-only hours to official opening hours.
