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

    # Seeded with the actual case id - otherwise the model has no way to
    # know WHICH referral/claim it is looking at. The system prompt is
    # generic (built once per problem, not per case); on the live backend
    # this first message is the only place a real id ever reaches the
    # model. Harmless on the scripted backend, which ignores transcript
    # entirely and replays pre-written moves regardless of its content.
    transcript = [{"role": "user", "content": "Case id: %s" % case_id}]
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

    # On the scripted backend ONLY, the gate auto-approves so the run stays
    # deterministic. The RECORD still shows the gate was reached and
    # passed, which is what a marker looks for. On the live backend, a
    # missing approval callback must NOT auto-approve - guardrails.gate()
    # already fails closed on approve=None (bool(None and ...) is False),
    # so leaving it None here is enough to correctly hold the booking. This
    # used to auto-approve unconditionally, which silently defeated the
    # "confirm" autonomy setting the moment BACKEND="live" - see
    # docs/CHANGELOG.md.
    if approve is None and backend.name == "scripted":
        approve = lambda action, payload: True

    try:
        while True:
            iterations += 1
            if iterations > config.MAX_TURNS + 2:
                raise GuardrailStop("step_cap", "loop did not terminate")

            move = _normalize_move(backend.next_move(transcript))
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
            calls = move["calls"]  # _normalize_move guaranteed this shape
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
            #
            # context.get(name) - not "name in context" - on purpose.
            # get_referral/check_referral_criteria/lookup_patient are all
            # documented to return None when the id/specialty they were
            # called with doesn't exist (a live model can call a real
            # tool with a WRONG value, not just a wrong shape - tools.call()
            # already handles a wrong shape). The key is still set in
            # context either way (context[name] = result runs
            # unconditionally), so "in context" is true even when the
            # value is None. Seen live (deepseek/deepseek-chat-v3.1):
            # check_referral_criteria(specialty=..., referral_id=...)
            # returned None, and resolve_routing() crashed on
            # criteria.get(...) - an AttributeError on 'NoneType', not a
            # gradeable record. A truthy check on the VALUE catches this;
            # a key-existence check does not.
            if (problem == "B" and resolved is None
                    and context.get("get_referral")
                    and context.get("check_referral_criteria")
                    and context.get("lookup_patient")):
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

    # Priced by whichever MODEL is actually configured, not a flat rate -
    # see config.PRICES. Scripted runs still use config.MODEL's price even
    # though no live call happened, exactly as before this change.
    price_in, price_out = config.price_for(config.MODEL)
    cost = (tokens_in / 1e6) * price_in + (tokens_out / 1e6) * price_out

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


def _normalize_move(move):
    """A live model's reply can be syntactically valid JSON and still be
    shaped wrong - missing 'tool'/'args', a 'calls' entry that isn't a
    [name, args] pair (a model unfamiliar with this exact convention
    might reasonably send {"tool": ..., "args": ...} objects instead of
    ["tool", {...}] arrays), or args that aren't a JSON object at all.
    Left unchecked, extracting calls from a move like that raises
    KeyError/ValueError/TypeError straight out of the loop below and
    crashes the WHOLE RUN, not just this move - the same failure class as
    the _parse_move and tools.call() fixes (see docs/CHANGELOG.md,
    2026-09-18). Normalise here into the SAME escalate shape _parse_move
    already uses for unparseable JSON, so one downstream code path -
    "if 'final' in move" - handles both kinds of failure identically.
    """
    if "final" in move:
        if isinstance(move["final"], dict):
            return move
        return {"final": {"decision": "escalate",
                          "reason": "model's 'final' was not a JSON object "
                                    "(got %s)" % type(move["final"]).__name__},
                "thought": (move.get("thought", "") + " [malformed final]").strip()}
    try:
        calls = move.get("calls") or [(move["tool"], move["args"])]
        calls = [(name, args) for name, args in calls]
        if not all(isinstance(args, dict) for _, args in calls):
            raise TypeError("a call's args was not a JSON object")
    except (KeyError, ValueError, TypeError) as e:
        return {"final": {"decision": "escalate",
                          "reason": "model returned a malformed action - %s" % e},
                "thought": (move.get("thought", "") + " [malformed move]").strip()}
    move["calls"] = calls
    return move
