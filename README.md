# PE6201 A2 — Team A-2 — Problem B

A single hand-rolled ReAct agent for outpatient referral coordination. For each
GP referral it decides **book** / **request information** / **escalate**,
against the routing table in Appendix A of the brief.

## Reproduce it (no key, no network, standard library only)

```bash
cd A2_scaffold
python3 run_eval.py
```

That runs every scripted case, grades it against the answer key, and writes
`results.json`. `BACKEND = "scripted"` is the committed default and stays that
way — only the D5(b) live battery needs an API key.

> Needs `A2_reference_data/` sitting next to `A2_scaffold/` (it does, in this
> repo). If you relocate it: `export A2_DATA=/path/to/A2_reference_data`.

## Where to start

| You want to… | Open |
|---|---|
| Understand what it does and why | `docs/HOW_IT_WORKS.pdf` |
| Run it / change it, step by step | `A2_scaffold/TEAM_RUN_GUIDE.ipynb` |
| See every test case, classified, and where the gaps are | `docs/TEST_CASE_MAP.md` |
| See what data was added and the bug that surfaced | `docs/DATA_NOTES.md` |
| See notable code fixes (who reported, what changed, how it was verified) | `docs/CHANGELOG.md` |
| See the live-battery model/tier plan and sign up for a slot | `docs/MODEL_BATTERY_PLAN.pdf` |
| See the actual rules-vs-model measured result (78.0% vs 37.3%, and why the gap is mostly labelling, not reasoning) | `docs/RULES_VS_MODEL_RESULTS.pdf` |
| Pick rule-based vs. model-based interactively | `python3 A2_scaffold/choose_mode.py` |
| Compare a rules-mode run against a model-mode run (pass rate, cost, route-mismatch count) | `python3 A2_scaffold/compare_modes.py results_rules_*.json results_model_*.json` |
| Run your D5(b) battery slot (smoke-tests first, stops before full spend if anything looks wrong) | `python3 A2_scaffold/run_battery_slot.py <your-model-slug>` |

## Layout

```
A2_scaffold/            the agent, tools, guardrails, harness, prompt, entry point
  config.py             BACKEND / MODEL / DECISION_MODE / guardrail limits
  tools.py              tool layer + resolve_routing() (the four gates as code)
  agent.py              the ReAct loop, instrumented
  guardrails.py         step cap · budget · de-dup · autonomy gate · route consistency
  prompt.py             system prompt, two variants for Problem B (rules / model)
  backends.py           scripted backend (per-case move scripts) + live
  run_eval.py           entry point — what a marker runs
  choose_mode.py        guided rules/model picker for the team
  compare_modes.py      reads two results.json files, prints the rules-vs-model table
  run_battery_slot.py   smoke-test + full battery for one D5(b) model, in one command
  demo_loop_failure.py  D7's method, worked once
  TEAM_RUN_GUIDE.ipynb  hands-on run guide
A2_reference_data/      fixtures, generators, answer key, integrity checker
docs/                   HOW_IT_WORKS (md + pdf), DATA_NOTES.md, build_pdf.py
```

## The one design decision worth knowing up front

`config.DECISION_MODE` is a switch: **`rules`** resolves the four gates in code
(`resolve_routing()`) with the model reporting the result; **`model`** has the
model apply the gates itself. Same tools and guardrails either way. A
route-consistency guardrail runs in both modes and blocks a booking if the
agent's conclusion and the code's own resolution disagree. The rationale, and
the measured comparison plan, are in `docs/HOW_IT_WORKS.pdf`.

## Status

Scripted backend: **all 50 labelled cases** (15 shipped + 35 added, across the
team) have a script and run for free. That's **118 graded trials** (negative
cases run 3×), all passing, in both decision modes. Every label independently
cross-checked against `resolve_routing`'s logic, not just checked for
existence. The rules-vs-model comparison is **done** (`openai/gpt-4o-mini`,
live, full set, both modes — see `docs/RULES_VS_MODEL_RESULTS.pdf`). The
D5(b) cross-model battery has its frontier slot done (`claude-opus-5`,
`REF-6007`, see `docs/MODEL_BATTERY_PLAN.pdf`) with 5 cheap/mid-tier slots
still open for the team. The guardrail checklist (D3b) is built
(`D3_guardrails-Cao Xiaohan/`). The judgement check (D4) is not started —
see the "what's still open" sections in `docs/DATA_NOTES.md` and the run
guide.
