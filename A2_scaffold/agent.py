"""
PE6201 · A2 scaffold — THE AGENT LOOP  (D1)
====================================================================
    thought -> action -> observation -> repeat -> final

That is the whole of ReAct, and it is hand-rolled here on purpose. No
framework owns your loop: when it misbehaves you need to be able to
read the twelve lines that did it.

WHAT MAKES THIS AN AGENT RATHER THAN A WORKFLOW: the number of steps is
decided by the DATA, not by you. A one-line claim with a live policy is
a short run. A four-line claim with a pre-authorisation to chase is a
long one. You did not write that branch - the record did.

--------------------------------------------------------------------
INSTRUMENTATION IS NOT OPTIONAL

Every run records turns, tokens, cost, every tool call and every
guardrail event. D6's cost model and D7's loop failure both need
numbers that were captured WHILE THE RUN HAPPENED. A team that adds
instrumentation afterwards has to run the whole battery again.

You cannot report a failure you had no way of noticing.
====================================================================
"""
import time

import config
import prompt
import tools
from backends import make_backend
from guardrails import Guardrails, GuardrailStop


def run_case(case_id, problem=None, approve=None, verbose=False):
    """Run ONE case from a clean state and return the decision record.

    ISOLATION (D4): everything this function needs is created inside it.
    No case may depend on a previous one having run - so no module-level
    counters, no shared guardrail object, no leftover transcript.
    """
    problem = problem or config.PROBLEM
    started = time.time()

    guards = Guardrails(config.MAX_TURNS, config.MAX_TOKENS_PER_RUN,
                        config.AUTONOMY)
    # WHAT THE MODEL IS TOLD. On the scripted backend these are ignored -
    # the moves are pre-written, so no prompt is ever sent. On the live
    # backend this IS the experiment D2(b) measures: the descriptors and
    # the routing rules, assembled by prompt.build_system_prompt().
    #     python3 run_eval.py --prompt      to see the exact text
    backend = make_backend(
        case_id,
        tool_descriptors=[tools.DESCRIPTORS[n] for n in tools.REGISTRY[problem]
                          if n in tools.DESCRIPTORS],
        system_prompt=prompt.build_system_prompt(problem))

    transcript = []      # what the model would see
    evidence = []        # every tool actually called, in order
    context = {}         # tool name -> its result, so resolve_routing can
                          # be computed once the facts it needs are in
    resolved = None       # tools.resolve_routing()'s result, once known -
                          # computed EVERY run regardless of DECISION_MODE.
                          # See config.py.

    # TURNS ARE TOOL-CALLING TURNS. The concluding move - where the agent
    # writes its decision record - is bookkeeping, not a turn. This is the
    # same convention Appendix A uses: CLM-8842 is "turns": 4 with EIGHT
    # tool calls, because the gated action is a turn like any other and
    # the write-up afterwards is not. Count them any other way and your
    # D2(c) arithmetic stops agreeing with the brief.
    turns = 0
    iterations = 0       # loop-safety only; never reported
    tokens_in = tokens_out = 0
    stopped_by = None

    # On the scripted backend the gate auto-approves so the run stays
    # deterministic. The RECORD still shows the gate was reached and
    # passed, which is what a marker looks for.
    if approve is None:
        approve = lambda action, payload: True

    try:
        while True:
            iterations += 1
            if iterations > config.MAX_TURNS + 2:
                raise GuardrailStop("step_cap", "loop did not terminate")

            move = backend.next_move(transcript)
            ti, to = backend.token_estimate(transcript)
            tokens_in, tokens_out = tokens_in + ti, tokens_out + to
            guards.check_budget(tokens_in + tokens_out)

            if verbose:
                label = ("conclude" if "final" in move else "turn %d" % (turns + 1))
                print("  %-9s · %s" % (label, move.get("thought", "")[:88]))

            # ---- conclude -------------------------------------------
            if "final" in move:
                record = dict(move["final"])
                # Non-blocking: escalating or asking wrongly isn't the
                # dangerous direction (that's what the whole autonomy-gate
                # argument is about), so this only LOGS a disagreement
                # rather than stopping the run. It is what lets you
                # measure, per config.DECISION_MODE, how often the model's
                # own reasoning would have diverged from the protocol even
                # on cases that never got near book_slot.
                if resolved is not None:
                    guards.note_mismatch(record.get("decision"),
                                         resolved["resolved_decision"])
                break

            # ---- act: one turn may carry SEVERAL calls ---------------
            turns += 1
            guards.check_turns(turns)

            # Only calls INDEPENDENT of each other belong in one turn.
            # A dependency chain cannot be shortened by running things at
            # once - that is why Problem B saves less than Problem A.
            calls = move.get("calls") or [(move["tool"], move["args"])]
            observations = []

            for name, args in calls:
                guards.check_duplicate(name, args)

                # THE GATE goes in front of the irreversible step only.
                # ROUTE CONSISTENCY sits at the same spot, in BOTH decision
                # modes: the agent is about to book, so its claim is "book" -
                # check it against what resolve_routing independently found,
                # regardless of what the agent was told or reasoned its way
                # to. This is what makes DECISION_MODE == "model" safe.
                if name == tools.GATED_ACTION.get(problem):
                    guards.check_route_consistency(
                        "book", resolved["resolved_decision"] if resolved else None)
                    if not guards.gate(name, args, approve):
                        raise GuardrailStop(
                            "gate_held",
                            "%s awaits human approval (autonomy=%s)"
                            % (name, config.AUTONOMY))

                result = tools.call(problem, name, args)
                evidence.append(name)
                context[name] = result
                observations.append({"tool": name, "args": args,
                                     "observation": result})
                if verbose:
                    print("       %-26s -> %s" % (name, _short(result)))

            # THE ROUTING DECISION. Computed EVERY run, in BOTH decision
            # modes, the moment both facts it needs are available - never
            # before, since it would be wrong to guess at a duplicate check
            # with no patient data yet. See config.DECISION_MODE.
            if (problem == "B" and resolved is None
                    and "check_referral_criteria" in context
                    and "lookup_patient" in context):
                resolved = tools.resolve_routing(
                    context["get_referral"]["specialty"],
                    context["check_referral_criteria"],
                    context["lookup_patient"],
                    tools.as_of())
                if config.DECISION_MODE == "rules":
                    # Only in "rules" mode does the model actually SEE this.
                    # In "model" mode it stays silent, computed purely so
                    # the consistency check above has something to compare
                    # against - the model reasons over the raw facts alone,
                    # exactly as the scaffold shipped by default.
                    observations.append({"tool": "resolve_routing",
                                         "args": {}, "observation": resolved})
                    if verbose:
                        print("       %-26s -> %s"
                             % ("resolve_routing (auto)", _short(resolved)))

            transcript.append({"role": "assistant",
                               "content": move.get("thought", "")})
            transcript.append({"role": "user",
                               "content": repr(observations)})

    except GuardrailStop as stop:
        # A LOUD STOP. The record says what halted the run and where, so
        # this never looks like a quiet wrong answer.
        stopped_by = stop.reason
        record = {"decision": "escalate",
                  "reason": "halted by the %s guardrail - %s"
                            % (stop.reason, stop.detail)}

    cost = (tokens_in / 1e6) * config.PRICE_IN + (tokens_out / 1e6) * config.PRICE_OUT

    record.update({
        "case_id": case_id,
        "evidence": evidence,
        "turns": turns,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost, 6),
        "seconds": round(time.time() - started, 3),
        "guardrails_fired": guards.fired,
        "stopped_by": stopped_by,
        "backend": backend.name,
        "decision_mode": config.DECISION_MODE if problem == "B" else None,
        "resolved_routing": resolved,
    })
    return record


def _short(value, n=64):
    s = repr(value)
    return s if len(s) <= n else s[:n - 1] + "…"
