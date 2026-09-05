"""
PE6201 · A2 scaffold — THE HARNESS  (D4, D5)
====================================================================
Load the answer key, run cases, grade them, report.

--------------------------------------------------------------------
THE TWO KINDS OF CHECK, AND WHY YOU NEED BOTH

A CODE CHECK compares the answer with your answer key.
    decision == expected_decision
    No model, no person, no opinion. Deterministic, free, instant.
    It is what produces the number.

A JUDGEMENT CHECK has someone read the record and decide.
    "Does the reason actually name the band and the window?"
    A PERSON can do it. A SECOND MODEL can do it. Same kind of check -
    the only difference is who grades. (This is what A1 called L1/L2.
    The names never mattered; the difference does.)

Why both: with three possible outcomes, a coin-flip scores 33% on the
code check alone. An agent can reach the right decision for the wrong
reason and the code check will not notice. `must_record` and `trigger`
are what stop a lucky run counting as a good one.

`prepare_judgement_check` below does NOT grade. It builds the queue a
human or a second model works through. Automating the judgement is
your design decision - and if you use a model, say so, because a model
grading a model is a claim that needs defending.
====================================================================
"""
import json
import os
import statistics

import config
from agent import run_case


# =====================================================================
# LOADING
# =====================================================================
def load_key(problem=None):
    """The answer key. YOURS, not ours, once you have extended it.

    Starts as 15 rows and grows by one per case you write. Same file
    throughout - the harness joins on case_id and does not care which
    rows we shipped and which you added.
    """
    problem = problem or config.PROBLEM
    path = os.path.join(config.data_root(),
                        "expected_outcomes_%s.json" % problem)
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    return {r["case_id"]: r for r in rows}


def load_cases(problem=None):
    """Every case id in the work queue, in file order."""
    problem = problem or config.PROBLEM
    table, field = (("referrals", "referral_id") if problem == "B"
                    else ("claims", "claim_id"))
    path = os.path.join(config.data_root(), "data_%s" % problem,
                        "%s.json" % table)
    with open(path, encoding="utf-8") as fh:
        return [r[field] for r in json.load(fh)]


# =====================================================================
# THE CODE CHECK
# =====================================================================
def code_check(record, expected):
    """Deterministic comparison. Returns (passed, [reasons it failed]).

    Note what is compared and what is NOT. The DECISION and its single
    TRIGGER are compared. The wording is not, the turn count is not, the
    cost is not - two agents can both be right and cost very different
    amounts, which is the subject of D6.
    """
    fails = []

    if record.get("decision") != expected.get("expected_decision"):
        fails.append("decision %r, expected %r"
                     % (record.get("decision"), expected.get("expected_decision")))

    # An escalation must escalate FOR THE RIGHT REASON. A run that
    # reaches the right outcome by the wrong trigger is not a pass - it
    # got there by luck and it will not get there next time.
    if expected.get("trigger"):
        if record.get("trigger") != expected["trigger"]:
            fails.append("trigger %r, expected %r"
                         % (record.get("trigger"), expected["trigger"]))

    # A booking must book the RIGHT slot. Problem B only.
    if expected.get("booked"):
        got = record.get("booked") or {}
        for field in ("clinic", "date", "time"):
            if got.get(field) != expected["booked"][field]:
                fails.append("booked.%s %r, expected %r"
                             % (field, got.get(field), expected["booked"][field]))

    return (not fails), fails


# =====================================================================
# THE JUDGEMENT CHECK
# =====================================================================
def prepare_judgement_check(record, expected):
    """Build ONE item for a human - or a second model - to rule on.

    This deliberately does not decide anything. `must_record` items are
    written in English and a substring match would be theatre, not a
    check. Someone reads the reason and answers yes or no per item.
    """
    return {
        "case_id": record["case_id"],
        "decision": record.get("decision"),
        "reason": record.get("reason", ""),
        "must_record": expected.get("must_record", []),
        "verdict": None,          # <- a person or a second model fills this
        "graded_by": None,        # <- "person: Priya" | "model: <name>"
    }


# =====================================================================
# RUNNING THE SET
# =====================================================================
def run_set(case_ids=None, problem=None, trials_for=None, verbose=False):
    """Run cases and grade them.

    `trials_for(case_id) -> int` decides how many trials each case gets.
    D4: ordinary cases get ONE trial; NEGATIVE cases get THREE, because
    negatives are the ones that flip between runs and a single trial
    cannot tell a real refusal from a lucky one.
    """
    problem = problem or config.PROBLEM
    key = load_key(problem)
    case_ids = case_ids or load_cases(problem)
    trials_for = trials_for or (lambda cid: 3 if _is_negative(key.get(cid)) else 1)

    results, judgement_queue = [], []

    for cid in case_ids:
        expected = key.get(cid)
        if expected is None:
            # check_my_data.py catches this before you get here. If you
            # are seeing it, run the checker.
            print("  SKIP %s - no label in the answer key" % cid)
            continue

        for trial in range(1, trials_for(cid) + 1):
            record = run_case(cid, problem=problem, verbose=verbose)
            passed, fails = code_check(record, expected)
            results.append({"case_id": cid, "trial": trial, "passed": passed,
                            "fails": fails, "record": record,
                            "family": expected.get("family")})
            if trial == 1:
                judgement_queue.append(prepare_judgement_check(record, expected))

    return results, judgement_queue


def _is_negative(expected):
    """A negative case is one whose correct outcome is anything except
    the act - so, an ask or an escalate."""
    if not expected:
        return False
    return expected.get("expected_decision") in (
        "escalate", "request_document", "request_information")


# =====================================================================
# REPORTING
# =====================================================================
def report(results):
    """The result table. EVERY pass rate is printed with its trial count,
    because a pass rate without one is not a measurement."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    turns = [r["record"]["turns"] for r in results]
    cost = sum(r["record"]["cost_usd"] for r in results)

    print()
    print("=" * 68)
    print("  RESULTS   %d of %d trials passed   (%.0f%%)"
          % (passed, total, 100.0 * passed / total if total else 0))
    print("=" * 68)
    print("  trials              %d" % total)
    print("  median turns        %s" % (statistics.median(turns) if turns else "-"))
    print("  worst case turns    %s" % (max(turns) if turns else "-"))
    print("  hit the step cap    %d"
          % sum(1 for r in results if r["record"]["stopped_by"] == "step_cap"))
    print("  total cost          US$%.4f   (%s backend)"
          % (cost, results[0]["record"]["backend"] if results else "-"))
    print()

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("  FAILED TRIALS - each one is either a bug or a wrong label:")
        for r in failures:
            print("    %-12s trial %d  [%s]" % (r["case_id"], r["trial"],
                                                r["family"]))
            for f in r["fails"]:
                print("        %s" % f)
        print()
        print("  Before you fix the agent, ask whether the LABEL is right.")
        print("  Test: could you justify the label to someone who had never")
        print("  seen your agent's output, using only Appendix A's routing")
        print("  table? If yes, the agent is wrong. If no, the label is.")
    else:
        print("  Every trial passed the code check.")
        print("  That is HALF the check. Work through the judgement queue")
        print("  before you believe this number.")
    print()
    return {"trials": total, "passed": passed,
            "pass_rate": passed / total if total else 0.0,
            "median_turns": statistics.median(turns) if turns else None,
            "cost_usd": cost}
