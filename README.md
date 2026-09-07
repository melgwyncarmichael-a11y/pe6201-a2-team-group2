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
| Pick rule-based vs. model-based interactively | `python3 A2_scaffold/choose_mode.py` |

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

Scripted backend: **11 of 25 cases** have a script (`REF-5602` plus our 10
additions) — the other 14 shipped cases still need one each. Those 11 produce
**21 graded trials** (negative cases run 3×), all passing in both decision
modes. Live battery, guardrail checklist (D3b), and the judgement check (D4)
are not started — see the "what's still open" sections in `docs/DATA_NOTES.md`
and the run guide.
