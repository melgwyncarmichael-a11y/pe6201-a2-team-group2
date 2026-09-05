#!/usr/bin/env python3
"""
PE6201 · A2 scaffold — PICK A DECISION MODE
====================================================================
    python3 choose_mode.py

For anyone on the team who doesn't want to dig through config.py: this
explains the two ways Problem B can resolve its four gates, asks which
one to run, and runs it. It does not edit config.py - your choice only
applies to this one run, exactly like `run_eval.py --mode ...` does.

This is a convenience wrapper, nothing more. `python3 run_eval.py` is
still what a marker actually runs, and it must keep working with zero
arguments - see run_eval.py's own docstring.
====================================================================
"""
import sys

import config
import run_eval

EXPLAIN = {
    "1": ("rules", """
  1 · RULE-BASED  (recommended default)
  --------------------------------------
  The four checks that decide a referral - red flag, right department,
  missing tests, a duplicate future appointment - are resolved by CODE,
  the instant the two lookups that gather the facts have both come back.
  The model is handed that resolution and just has to report it and act
  on it faithfully.

  Cheaper (fewer tokens spent reasoning about something a lookup already
  answered), fully deterministic on anything the shipped protocol data
  covers, and every decision can be traced to one exact line of code
  that produced it. A safety check (guardrails.py) still runs
  underneath even in this mode and would block a booking if it and the
  code's own resolution ever disagreed - it shouldn't, in this mode, by
  construction, but the check runs anyway.
"""),
    "2": ("model", """
  2 · MODEL-BASED  (what the brief's architecture section is written
                    assuming happens)
  --------------------------------------
  The model reads the same raw facts - the red-flag term if any, whether
  the department matches, which tests are missing, the patient's
  existing appointments - and applies the four-gate rule ITSELF, in its
  own reasoning, on every single case.

  More expensive per case, and its correctness under a hostile referral
  (one whose text tries to talk it into ignoring a red flag, say) is
  something you have to prove with eval and guardrail cases rather than
  something true by construction. The SAME safety check runs underneath
  this mode too, and is the actual reason this mode is safe to run at
  all: a hostile instruction can talk the model into concluding "book",
  but it cannot make the code's own resolution agree, and booking is
  gated on agreement, not on what the model said.
"""),
}


def ask():
    print("=" * 68)
    print("  PE6201 · A2 · Problem B — which way should the four gates be")
    print("  resolved for this run?")
    print("=" * 68)
    for key, (_, text) in sorted(EXPLAIN.items()):
        print(text)
    print("=" * 68)
    while True:
        choice = input("  Pick 1 or 2 (or type rules / model), "
                       "blank = keep config.py's current setting: ").strip().lower()
        if choice == "":
            print("  Keeping config.py's current DECISION_MODE = %r\n"
                 % config.DECISION_MODE)
            return config.DECISION_MODE
        if choice in EXPLAIN:
            return EXPLAIN[choice][0]
        if choice in ("rules", "model"):
            return choice
        print("  Didn't catch that - type 1, 2, rules, model, or leave it blank.")


def main(argv):
    mode = ask()
    print("  Running with DECISION_MODE = %r\n" % mode)
    # Reuse run_eval's real entry point so this is never a second code path
    # to keep in sync - it IS run_eval.py, just asked first.
    return run_eval.main([argv[0], "--mode", mode] + argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
