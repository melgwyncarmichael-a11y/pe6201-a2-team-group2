# Changelog

Notable code-level fixes and why they happened — separate from
`DATA_NOTES.md` (which tracks fixture/eval-case changes). One entry per
reported issue: who found it, what was actually wrong, what changed, how it
was verified. Newest first.

---

## 2026-09-17 — Three teammate-added cases (`REF-6023`, `REF-6027`, `REF-6030`) mislabelled by a synonym gap

**Found by:** the independent `resolve_routing` cross-check this repo runs
against every label (not just `check_my_data.py`'s existence check) — see
`docs/TEST_CASE_MAP.md` / `docs/DATA_NOTES.md` for the method.

**The bug:** all three referrals described a cardiology complaint as
*"shortness of breath"* or *"dyspnea"* — clinically identical to
`"breathlessness"`, but not the literal substring `check_referral_criteria`
matches against CARD's `treats` list. So `right_department` came back
`False`, and each case actually resolved to `escalate`/`specialty_mismatch`
**before** it ever reached the check the case was written to test:

- `REF-6023` — labelled `request_information`/BNP-01; actually resolved to
  `escalate`/`specialty_mismatch`.
- `REF-6027` — same root cause, same actual resolution.
- `REF-6030` — labelled `book`; actually resolved to
  `escalate`/`specialty_mismatch`. This one visibly failed the code check
  (`117/118`) because its script tries `book_slot`, which the
  route-consistency guardrail correctly blocked — the guardrail doing
  exactly its job, not a separate bug.

**A second, independent bug found on `REF-6030` while fixing the first:**
its script called `lookup_patient` with `patient_id: "P-1233"`, but the
referral's actual `patient_id` is `P-1215`. The scripted backend doesn't
cross-check that a call's arguments match the referral it's for, so this
ran without erroring — it just quietly looked up the wrong patient. Didn't
change this case's outcome (neither patient has a conflicting appointment),
but the decision record would have cited the wrong patient's duplicate
check.

**The fix:**
- `make_fixtures_B.py` — replaced "shortness of breath"/"dyspnea" with
  "breathlessness" in all three `clinical_summary` fields. No other change
  to the referrals (specialty, tests, patient, dates all untouched).
- `backends.py` (`REF-6030`) — corrected `lookup_patient`'s `patient_id` to
  `P-1215`, and updated its `reason`/`thought` text: the actual matching
  urgency trigger is `"rapidly worsening"`, not `"worsening over days"`
  (both are valid urgent-band triggers in the text, but only one is
  actually present — the label had cited the wrong one).
- `expected_outcomes_B.json` — same trigger-wording correction in
  `REF-6030`'s `must_record`.

**Verified:**
- `check_my_data.py` → "Your data hangs together."
- Independent `resolve_routing` cross-check, all 50 labelled cases:
  **0 mismatches** (was 3).
- `run_eval.py --mode rules` and `--mode model`, full set:
  **118/118 trials, 100%**, both modes (was 117/118).

---

## 2026-09-17 — Autonomy gate silently auto-approved on the live backend

**Reported by:** the guardrails owner, reviewing `agent.py` while building
the D3(b) guardrail checklist (13 tests passing at the time of report).

**The report:** `agent.py`'s comment said the auto-approval fallback was
"for the scripted backend," but the code applied it unconditionally:

```python
if approve is None:
    approve = lambda action, payload: True
```

Since `harness.py`/`run_eval.py` never pass an `approve` callback at all,
*every* run - scripted or live - hit this fallback. In `AUTONOMY="confirm"`
mode, that meant a live run with no approval wiring would silently auto-book
instead of holding, defeating the whole point of the confirm gate.

**Verified before changing anything:**
- `guardrails.py`'s `gate()` already fails closed on its own -
  `bool(approve and approve(...))` is `False` when `approve is None`. No
  change needed there.
- The *only* thing causing the bypass was `agent.py`'s override turning
  `None` into an always-`True` lambda before it ever reached `gate()`.
- `backend = make_backend(...)` is already constructed earlier in
  `run_case()`, so `backend.name` was available to condition on without
  restructuring anything.

**The fix** (`agent.py`, `run_case()`): the fallback now only fires when
`backend.name == "scripted"`:

```python
if approve is None and backend.name == "scripted":
    approve = lambda action, payload: True
```

On the live backend, a missing `approve` now stays `None`, and `gate()`'s
existing logic holds the booking correctly.

**Regression check** — scripted backend, both decision modes, full 50-case
set: **117/118 trials, unchanged** from before the fix (the one failing
trial, `REF-6030`, is a separate known issue - see the repo's recent commit
history, unrelated to this change).

**New-behaviour check** — simulated a live backend replaying a real,
correct move sequence (`REF-5620`, which genuinely resolves to "book") with
no `approve` callback supplied:

```
decision: escalate
stopped_by: gate_held
guardrails_fired: [{'guardrail': 'gate_held', 'detail': 'book_slot (autonomy=confirm)'}]
```

Confirms the booking now correctly holds instead of silently going through.

**Downstream implication, not yet acted on:** once the live battery (D5b)
actually runs, whoever calls `run_case`/`run_set` against `BACKEND="live"`
needs to explicitly supply an `approve` callback (e.g.
`lambda a, p: True`, mirroring what the scripted path did implicitly) if
the goal is measuring *decision quality* rather than exercising the real
approval flow. Without it, every live "book" case will now correctly show
as held/escalated - which is the right safety behaviour, but will read as a
lower pass rate if nobody accounts for it. Worth deciding before the live
battery is run, not after.

**Next step (owned by the reporter):** add a guardrail-checklist case for
the missing-approval-holds behaviour and rerun the D3 checklist.
