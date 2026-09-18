#!/usr/bin/env python3
"""
PE6201 · A2 scaffold — RULES vs MODEL comparison reader
====================================================================
Reads two results.json files - one per DECISION_MODE, same model, same
eval set - and prints the table the D0/D6 argument is actually built on:
pass rate, turns, tokens, cost, and how often each mode's own conclusion
disagreed with what resolve_routing() independently computed.

    python3 compare_modes.py results_rules_<model>.json results_model_<model>.json

This does not care what model produced the files or whether the backend
was scripted or live - only that both came from the SAME model and the
SAME eval set (your job to keep that true; see
docs/MODEL_BATTERY_PLAN.md §2 for the run commands that produce them).
====================================================================
"""
import json
import statistics
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def guardrail_count(record, name):
    return sum(1 for g in record.get("guardrails_fired", []) if g.get("guardrail") == name)


def stats(data):
    results = data["results"]
    records = [r["record"] for r in results]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    turns = [r["turns"] for r in records]

    stopped = {}
    for r in records:
        if r.get("stopped_by"):
            stopped[r["stopped_by"]] = stopped.get(r["stopped_by"], 0) + 1

    return {
        "config": data.get("config", "?"),
        "trials": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "median_turns": statistics.median(turns) if turns else None,
        "worst_turns": max(turns) if turns else None,
        "tokens_in": sum(r["tokens_in"] for r in records),
        "tokens_out": sum(r["tokens_out"] for r in records),
        "cost_usd": sum(r["cost_usd"] for r in records),
        # THE number this whole comparison exists to measure: how often
        # does each mode's own conclusion disagree with what
        # resolve_routing() independently computed? "route_mismatch" is
        # the hard block (it stopped an attempted book_slot);
        # "route_mismatch_nonblocking" is a logged-only disagreement on
        # an escalate/ask outcome, which never touches book_slot at all.
        "route_mismatch": sum(guardrail_count(r, "route_mismatch") for r in records),
        "route_mismatch_nonblocking":
            sum(guardrail_count(r, "route_mismatch_nonblocking") for r in records),
        "stopped_by": stopped,
    }


def fail_diff(a_data, b_data):
    """(case_id, trial) pairs where one mode passed and the other did
    not - the cases where DECISION_MODE actually changed the OUTCOME,
    not just the cost. Everything else in this comparison is cost/turns;
    this is correctness."""
    def index(data):
        return {(r["case_id"], r["trial"]): r["passed"] for r in data["results"]}
    a_idx, b_idx = index(a_data), index(b_data)
    diffs = []
    for key in sorted(set(a_idx) | set(b_idx)):
        av, bv = a_idx.get(key), b_idx.get(key)
        if av != bv:
            diffs.append((key, av, bv))
    return diffs


def row(label, a, b):
    print("  %-30s %16s %16s" % (label, a, b))


def main(argv):
    if len(argv) != 3:
        print("\n  usage: python3 compare_modes.py "
              "<rules_results.json> <model_results.json>\n")
        return 1

    a_path, b_path = argv[1], argv[2]
    a_data, b_data = load(a_path), load(b_path)
    a, b = stats(a_data), stats(b_data)

    print()
    print("=" * 68)
    print("  RULES vs MODEL")
    print("    rules: %s" % a_path)
    print("    model: %s" % b_path)
    print("=" * 68)
    print("    rules config: %s" % a["config"])
    print("    model config: %s" % b["config"])
    print()
    row("", "rules", "model")
    row("trials", a["trials"], b["trials"])
    row("passed", a["passed"], b["passed"])
    row("pass rate", "%.1f%%" % (100 * a["pass_rate"]), "%.1f%%" % (100 * b["pass_rate"]))
    row("median turns", a["median_turns"], b["median_turns"])
    row("worst turns", a["worst_turns"], b["worst_turns"])
    row("tokens in (total)", a["tokens_in"], b["tokens_in"])
    row("tokens out (total)", a["tokens_out"], b["tokens_out"])
    row("cost (total)", "US$%.4f" % a["cost_usd"], "US$%.4f" % b["cost_usd"])
    print()
    print("  THE NUMBER THIS COMPARISON EXISTS TO MEASURE:")
    row("route_mismatch (blocked a book)", a["route_mismatch"], b["route_mismatch"])
    row("route_mismatch_nonblocking (logged only)",
        a["route_mismatch_nonblocking"], b["route_mismatch_nonblocking"])
    print()
    print("  stopped_by breakdown:")
    keys = sorted(set(a["stopped_by"]) | set(b["stopped_by"]))
    if not keys:
        print("    (nothing stopped either run)")
    for k in keys:
        row(k, a["stopped_by"].get(k, 0), b["stopped_by"].get(k, 0))

    diffs = fail_diff(a_data, b_data)
    print()
    if diffs:
        print("  CASES WHERE PASS/FAIL DIFFERED BETWEEN MODES (%d):" % len(diffs))
        for (case_id, trial), av, bv in diffs:
            print("    %-12s trial %d   rules passed=%-5s model passed=%-5s"
                  % (case_id, trial, av, bv))
    else:
        print("  No case+trial differed in pass/fail between modes - any")
        print("  difference above is cost/turns only, not correctness.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
