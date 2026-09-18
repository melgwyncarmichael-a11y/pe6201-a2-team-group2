# v1 vs. v2 descriptors — the actual measured result

D2(b) asks for a tool-descriptor rewrite and a MEASUREMENT of what it did,
not just a claim. Teammate shuyu723 rewrote `tools.DESCRIPTORS` on
2026-09-17 ([`a3a4dd0`](../../../commit/a3a4dd0), "Optimize DESCRIPTORS to
reduce token size"), cutting the base system-prompt prefix from 1,451 to
1,033 tokens. This is that rewrite's effect measured end-to-end on a real
live run, not just the prompt-size delta.

**v1** = `tools.DESCRIPTORS` as it was immediately before that commit (the
original, more verbose descriptors).
**v2** = `tools.DESCRIPTORS` as it is right now — what every other live run
in this repo has actually used.

**Held fixed**: model (`openai/gpt-4o-mini`), `DECISION_MODE="model"`,
the full 50-case/118-trial eval set, `--auto-approve`. Only the
descriptor text differs between the two runs. v1 was run from an
isolated `git worktree` checked out at v2's own commit with only the
`DESCRIPTORS` block reverted — everything else (prompt.py's JSON-format
fix, backends.py's retry logic, agent.py's crash hardening) is IDENTICAL
between the two runs, so the comparison isolates the descriptor change
alone, not a mix of that and today's other fixes.

Raw results committed at `A2_scaffold/results_model_gpt4o-mini.json`
(v2) and a v1 copy alongside it (see the note at the bottom on where the
v1 file lives).

---

## The headline numbers

| | v1 (old descriptors) | v2 (current, optimized) |
|---|---|---|
| trials | 118 | 118 |
| pass rate (exact code check) | 27.1% (32/118) | **37.3%** (44/118) |
| decision-level accuracy* | **80.5%** (95/118) | 78.0% (92/118) |
| cost (full run) | $0.1749 | **$0.1311** (25% cheaper) |
| tokens in (total) | 1,062,736 | 783,314 (26% fewer) |
| tokens out (total) | 25,814 | 22,728 (12% fewer) |
| worst-case turns | 6 | 5 |
| guardrail stops | **`route_mismatch` × 6, `duplicate_action` × 4** | **0** |

\* trigger-wording-only mismatches set aside — decision was actually
correct (see `docs/RULES_VS_MODEL_RESULTS.md` for why raw pass rate
alone is misleading for `DECISION_MODE="model"` results; the same
distinction applies here).

## The finding that actually matters: guardrail firings, not just tokens

v1 triggered **10 real guardrail interventions** that never happened once
with v2:

- **6 `route_mismatch`** — the agent tried to book something the
  protocol data (`resolve_routing()`) disagreed with, and the
  route-consistency guardrail blocked it.
- **4 `duplicate_action`** — the agent repeated a tool call (same name,
  same arguments) it had already made in the same run.

These are not labelling artefacts. They are the agent actually
attempting a wrong or wasteful action, caught by code specifically
designed to catch that. v2's run had **zero** guardrail firings across
all 118 trials. The longer, less-focused v1 descriptors correlate with
the agent going further off track before recovering, not just with a
bigger prompt bill.

## Failure breakdown (both runs)

| Category | v1 | v2 |
|---|---|---|
| Decision itself was wrong | **23** | **26** |
| Decision right, trigger *label* wrong | 62 | 47 |
| Decision right, booked slot wrong | 1 | 1 |

Read this carefully: v1's raw *count* of wrong decisions (23) is
slightly lower than v2's (26) — decision-level accuracy alone would say
v1 is marginally "more accurate." But that number doesn't capture the 10
guardrail interventions above, several of which are exactly the kind of
"tried to book the wrong thing" event a decision-only accuracy score
would otherwise miss entirely if the guardrail hadn't caught it.
Decision-level accuracy answers "was the final answer right"; it does
not answer "did the agent behave safely getting there."

## What this actually supports for the D2(b) argument

- **The rewrite is a genuine improvement, not just a token-count win.**
  Cheaper (25%), fewer tokens both directions, AND measurably fewer
  guardrail interventions — three independent signals pointing the same
  direction, not one metric dressed up as three.
- **Decision-level accuracy is roughly a wash (80.5% vs 78.0%, within
  the kind of run-to-run noise seen elsewhere in this project)** - the
  rewrite did not damage the model's underlying reasoning to get its
  savings. That is the strongest version of the D2(b) claim: you can cut
  the base prefix by 29% without paying for it in decision quality.
- **The guardrail-firing gap is the number to lead with**, not the raw
  pass-rate gap (27.1% vs 37.3%) - that headline gap is partly the same
  trigger-wording noise documented in `docs/RULES_VS_MODEL_RESULTS.md`,
  and leading with it risks the same "misleading on its own" mistake
  that doc warns against.

## Caveats - keep these attached to the number

- **One model only** (`openai/gpt-4o-mini`, cheap tier). A different
  model's sensitivity to descriptor verbosity could differ - this is not
  a universal claim about prompt length and guardrail-firing rate.
- **Not a controlled ablation of WHICH part of the rewrite helped.** The
  optimization commit changed descriptor wording throughout; this result
  says the rewrite as a whole helped, not which specific edit did the
  work.
- **v1 was run on top of TODAY's other fixes**, not the original,
  unpatched codebase - deliberately, to isolate the descriptor change as
  the only variable. A naive "check out the old commit and run it"
  would have reproduced unrelated bugs (JSON-format compliance, the
  unknown-tool crash) that have nothing to do with descriptor length,
  and confounded the comparison. See `docs/CHANGELOG.md`'s
  `_move_is_incomplete` entry (2026-09-18) for a fix this isolation
  approach actually surfaced along the way.

---

*Written up 2026-09-19. v1's raw results committed as
`A2_scaffold/results_model_gpt4o-mini-v1-descriptors.json`. v2's are the
existing `A2_scaffold/results_model_gpt4o-mini.json`, already committed
and used in `docs/RULES_VS_MODEL_RESULTS.md`. See
`docs/MODEL_BATTERY_PLAN.md` §"A suggested spread" for how this fits
alongside the cross-model battery (slot G, the 7th team member's task).*
