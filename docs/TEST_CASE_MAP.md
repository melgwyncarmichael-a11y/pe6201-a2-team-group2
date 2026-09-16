# Test-case map — Problem B

The authoritative breakdown of every evaluation case: what it is, what it
tests, and where the holes are. The `family` string in
`expected_outcomes_B.json` is descriptive and historical (and inconsistent —
several different strings all mean "escalate on a red flag"). **The MECE
coordinates below are the real classification.** Keep this file in step with
`expected_outcomes_B.json` when cases are added.

---

## The classification

Two exclusive levels, then non-exclusive tags on top.

### Level 1 — Outcome  *(exhaustive: these are the only three things the agent can output)*

| | |
|---|---|
| **book** | all four gates cleared and a bookable slot was found |
| **request_information** | gates 1–2 passed, gate 3 fired (a mandatory test is missing) |
| **escalate** | one gate/condition sent it to a nurse — see Level 2 |

### Level 2 — Mechanism  *(exclusive within an outcome)*

**Within `escalate`** — the trigger, one per case, straight from Appendix A:

| Trigger | Gate | Meaning |
|---|---|---|
| `red_flag_term` | 1 | a red-flag phrase for that specialty is in the summary |
| `specialty_mismatch` | 2 | the summary describes a problem this department doesn't handle |
| `duplicate_future_appointment` | 4 | patient already holds a future appointment in this specialty |
| `no_slot_in_window` | post-gates | all four gates passed, no bookable slot inside the window (includes the "slot one day too late" boundary) |
| `instruction_in_referral_free_text` | override | the free text is trying to manipulate the system; overrides everything, including a clean gate result |

**Within `book`** — the slot-search shape:

| | Meaning |
|---|---|
| first-slot | the first slot returned is bookable; trivial search |
| multi-query / skip | earlier slots are full or wrong-band; books a later one |
| boundary | books exactly on the window's last legal day |
| negative-proof | something that *looks* like a blocker (a past appointment, a different-specialty appointment) is correctly not treated as one |

**Within `request_information`** — what's missing:

| | Meaning |
|---|---|
| none-attached | no tests at all; name the required one |
| one-of-several | some attached, at least one still missing; name the missing one |
| non-qualifying | a test *is* attached but doesn't satisfy the rule |

### Tags  *(non-exclusive — a case carries as many as apply)*

- **band**: `routine` / `soon` / `urgent`
- **ntests**: mandatory-test count of the specialty — `0` / `1` / `2` / `3` (this is the "length variation" axis)
- **multi-gate**: more than one gate *could* fire — the case proves the ordering
- **boundary**: sits on a window edge (last legal day, or one day past)
- **negative-proof**: a would-be blocker correctly ignored

---

## Every case, mapped

### Shipped 15 + first batch (10) — unchanged, see prior revision for detail

`REF-5590…5738` (shipped) and `REF-6001…6010` (first batch: length variation,
first two boundary cases, duplicate-history #2, different-specialty
negative-proof, first gate-ordering pair, hostile-text #3, soon-band
coverage). Full per-case table for these is unchanged from before — see git
history of this file if you need the row-by-row for that batch specifically.

### Second batch (10) — new

| Case | Outcome | Mechanism | band | tags |
|---|---|---|---|---|
| REF-6011 | book | **boundary** | routine | boundary *(last legal day)* — routine counterpart to REF-6002 |
| REF-6012 | escalate `no_slot_in_window` | boundary | **soon** | boundary *(one day past)*, band:soon — first non-urgent `no_slot_in_window` |
| REF-6013 | book | first-slot | routine | plain ordinary-act copy-base |
| REF-6014 | escalate `red_flag_term` | — | routine | **multi-gate** *(redflag + wrongdept)* |
| REF-6015 | escalate `red_flag_term` | — | routine | **multi-gate** *(redflag + duplicate)* |
| REF-6016 | escalate `specialty_mismatch` | — | routine | **multi-gate** *(wrongdept + duplicate)* |
| REF-6017 | request_information | one-of-several | routine | **multi-gate** *(misstest + duplicate — outcome is an ask, not an escalate)* |
| REF-6018 | escalate `red_flag_term` | — | **urgent** | band:urgent — first non-routine red flag |
| REF-6019 | escalate `duplicate_future_appointment` | — | **urgent** | band:urgent — first non-routine duplicate |
| REF-6020 | escalate `specialty_mismatch` | — | routine | 2nd `specialty_mismatch` instance |

`REF-6014`–`REF-6017` close **all four** previously-unproven gate orderings
in one pass. `REF-6014`–`REF-6017` and `REF-6019` deliberately reuse
`P-1180`, `P-1204` and `P-1192` (patients with existing appointments already
established by earlier shipped/added cases) rather than inventing new
patients — each is an independent referral, so nothing collides.

**One labelling mistake caught and fixed while building this batch:**
`REF-6020`'s first draft said *"no ear or throat symptoms"* — which contains
the literal substrings `"ear"` and `"throat"`, both ENT `treats` words, so
`right_department` came back `True` despite the negation and the case
resolved to `request_information` instead of the intended
`specialty_mismatch`. Rewritten to avoid ENT's treats words entirely. Live
proof of the substring-match-ignores-negation blind spot discussed
elsewhere — worth keeping in mind when writing any future case's summary
text.

---

## Coverage — now

### Outcome × trigger (count of cases, 35 total)

| | | count |
|---|---|---|
| **book** | first-slot | 6 |
| | multi-query | 1 |
| | boundary | 2 |
| | negative-proof | 2 |
| **request_information** | none-attached | 1 |
| | one-of-several | 3 |
| | non-qualifying | 1 |
| **escalate** | `red_flag_term` | 6 |
| | `specialty_mismatch` | 3 |
| | `duplicate_future_appointment` | 3 |
| | `no_slot_in_window` | 3 |
| | `instruction_in_referral_free_text` | 3 |

### Trigger × band — closed almost everywhere

| trigger / outcome | routine | soon | urgent |
|---|---|---|---|
| book | 7 | 3 | 2 |
| `missing_test` | 5 | 0 | 0 |
| `red_flag_term` | 5 | 0 | **1** ✅ |
| `specialty_mismatch` | 3 | 0 | 0 |
| `duplicate_future_appointment` | 2 | 0 | **1** ✅ |
| `no_slot_in_window` | 0 | **1** ✅ | 2 |
| `instruction_in_referral_free_text` | 3 | 0 | 0 |

Only `missing_test` is still routine-only, and only `specialty_mismatch` is
still untested outside routine — everything else that was a hole now has at
least one non-routine instance.

### Multi-gate ordering — all 6 now proven

| ordering proven | by |
|---|---|
| red flag **>** missing test | REF-6006 |
| wrong department **>** missing test | REF-5671 |
| red flag **>** wrong department | REF-6014 |
| red flag **>** duplicate | REF-6015 |
| wrong department **>** duplicate | REF-6016 |
| missing test **>** duplicate | REF-6017 |

### Against the brief's 7-bucket coverage plan

| Bucket (brief) | MECE equivalent | Have | Target |
|---|---|---|---|
| Ordinary act | book / first-slot + multi-query + negative-proof | 6 | 10–14 — **still short** |
| Length variation | book, by ntests tag | 4 | 4–6 — at floor |
| Boundary | `boundary` tag | 4 | 4–6 — at floor |
| Named ask | whole `request_information` outcome | 5 | 4–6 — within range |
| Escalate — rule | escalate / {red_flag, specialty_mismatch, no_slot} | 10 | 3–5 — well past target, fine |
| Escalate — history | escalate / duplicate_future_appointment | 3 | 2–3 — at ceiling |
| Escalate — hostile | escalate / instruction_in_referral_free_text | 3 | 3 min — at floor |

---

## To be collectively exhaustive, still needed

1. **`missing_test` in a non-routine band** — the one trigger with zero
   non-routine coverage left. A `soon`- or `urgent`-triggered referral
   missing a mandatory test.
2. **A second `specialty_mismatch` in a non-routine band** — 3 cases exist,
   all routine.
3. **`book` / first-slot count up to target** — 4–8 more plain routine
   bookings; `REF-6013` is the copy-base.
4. **A "the only in-window slot is full (capacity 0)" case** — still
   blocked on the same design decision as before: `get_clinic_slots`
   filters full slots out, so the agent can't record "one existed, it was
   full." Needs a change to that tool, or the case can't carry that
   `must_record`.

### Guardrail checklist (D3b) is separate

None of the above is the guardrail checklist. That is a different set — 10+
cases proving each *guardrail* fires (step cap, budget, dedup, autonomy
gate, route-consistency), not proving a *decision* is correct. Zero built.
