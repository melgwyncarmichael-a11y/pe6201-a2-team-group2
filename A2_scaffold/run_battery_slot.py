#!/usr/bin/env python3
"""
PE6201 · A2 scaffold — BATTERY SLOT RUNNER  (D5b convenience wrapper)
====================================================================
    python3 run_battery_slot.py <model-slug>

Automates the smoke-test-then-full-battery workflow every D5(b) slot
needs, established 2026-09-18 after real live bugs proved this checkpoint
catches real problems before they cost money (see docs/CHANGELOG.md):
a model narrating prose instead of JSON, a hallucinated tool call, a
wrong OpenRouter slug. Every one of those showed up on the FIRST smoke-
test case, not the 50th - a script that skipped straight to the full
battery would have burned real money and time on all three, and the
wrong-slug one would have failed instantly anyway (HTTP 400).

WHAT IT DOES, IN ORDER:
  1. Runs ONE live case (REF-5590, --mode model) and checks the output
     for the known failure signatures this project has actually hit.
  2. If anything looks wrong, STOPS. No full-battery spend without a
     human reading why first.
  3. If it looks clean, runs the full 118-trial battery
     (--all --auto-approve) and saves results_model_<model>.json.

WHAT IT DOES NOT DO: decide whether the PASS RATE is good, or explain a
decision-level-accuracy breakdown (see docs/RULES_VS_MODEL_RESULTS.md for
why raw pass rate alone is misleading for DECISION_MODE="model"). Read
the saved results file, or hand it to whoever is doing that analysis.

Needs OPENROUTER_API_KEY exported and the model's price already in
config.PRICES - both already fail loudly on their own if missing, this
script does not duplicate those checks.
====================================================================
"""
import os
import subprocess
import sys

SMOKE_CASE = "REF-5590"

# Every failure signature this project has actually hit live, not a
# guessed list - see docs/CHANGELOG.md for each one's incident.
KNOWN_BAD_SIGNS = [
    "did not return parseable JSON",       # prose instead of JSON
    "no usable content",                   # content: null
    "malformed action",                    # bad calls/tool/args shape
    "was not a JSON object",               # malformed 'final'
    "unknown_tool",                        # hallucinated tool name
    "bad_arguments",                       # wrong tool argument shape
    "No price entered for MODEL",          # config.PRICES missing this model
    # "unparseable:" only prints once the self-correction retry has
    # ALREADY been tried and failed (see backends.py) - it's a reliable
    # "this trial gave up" signal, not a guess. Added after
    # mistralai/mistral-small-3.2-24b-instruct's smoke test showed this
    # in 2 of 3 trials' turn traces (only trial 1's full DECISION RECORD
    # prints "did not return parseable JSON" verbatim - the other
    # trials' failures were invisible to this list until now) and the
    # smoke test still called itself "clean".
    "unparseable:",
    "Traceback (most recent call last)",   # anything else uncaught
]


def run(cmd):
    print("  $ %s" % " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr[-2000:])
    return result


def main(argv):
    if len(argv) != 2:
        print("\n  usage: python3 run_battery_slot.py <model-slug>\n")
        return 1
    model = argv[1]

    print("\n  SMOKE TEST - %s on %s\n" % (SMOKE_CASE, model))
    smoke = run(["python3", "run_eval.py", "--backend", "live",
                "--model", model, "--mode", "model", SMOKE_CASE])
    bad = [s for s in KNOWN_BAD_SIGNS if s in smoke.stdout or s in smoke.stderr]
    if smoke.returncode not in (0, 1) or bad:
        # returncode 1 alone is fine - that's just "code check failed",
        # which is normal (trigger-wording mismatches are EXPECTED in
        # model mode, see docs/RULES_VS_MODEL_RESULTS.md). A genuine
        # crash or a known bad sign is what actually stops this.
        print("  SMOKE TEST FAILED - %s" % (", ".join(bad) or
              "process exited %d" % smoke.returncode))
        print("  Stopping before any full-battery spend. Fix this first,")
        print("  then re-run this script.")
        return 1

    # Remove any pre-existing results.json BEFORE the full battery runs.
    # If it crashes partway and never writes a fresh one, there is then
    # nothing left for `mv` to silently pick up instead - this exact
    # gap once let a crashed run look like a completed one with a real
    # (but wrong) pass rate (docs/CHANGELOG.md, 2026-09-18: the
    # gpt-4o-mini rules-vs-model incident). Checking returncode/known-bad-
    # signs alone was not enough THIS time either: a missing-price
    # SystemExit exits with code 1, identical to an ordinary code-check
    # failure, and slipped past the smoke test until "No price entered"
    # was added to KNOWN_BAD_SIGNS above.
    if os.path.exists("results.json"):
        os.remove("results.json")

    print("\n  Smoke test clean. Running the full battery (--all, ~118")
    print("  trials, several minutes)...\n")
    full = run(["python3", "run_eval.py", "--backend", "live",
               "--model", model, "--mode", "model", "--all", "--auto-approve"])
    bad = [s for s in KNOWN_BAD_SIGNS if s in full.stdout or s in full.stderr]
    if full.returncode not in (0, 1) or bad or not os.path.exists("results.json"):
        reason = (", ".join(bad) if bad else
                  "no results.json written" if not os.path.exists("results.json") else
                  "process exited %d" % full.returncode)
        print("  FULL BATTERY FAILED - %s" % reason)
        print("  Not saving anything. Read the output above before retrying.")
        return 1

    safe_name = model.replace("/", "-")
    out_name = "results_model_%s.json" % safe_name
    run(["mv", "results.json", out_name])
    print("\n  Saved %s" % out_name)
    print("  Commit it, and share the pass rate / cost with whoever is")
    print("  tracking docs/MODEL_BATTERY_PLAN.md's results table.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
