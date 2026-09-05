"""
PE6201 · A2 scaffold — THE GUARDRAIL LAYER  (D3a)
====================================================================
Five things, and NONE of them involve trusting a model's word for it.

    1. STEP CAP            stop after N turns
    2. BUDGET CEILING      stop after N tokens
    3. ACTION DE-DUPLICATION   stop repeating an action already taken
    4. AUTONOMY GATE       hold the irreversible step for a human
    5. ROUTE CONSISTENCY   block the irreversible step if the agent's own
                           conclusion disagrees with what the protocol
                           data actually resolves to

A model cannot influence whether the first four fire, which is why
D3(b)'s ten guardrail cases run on the SCRIPTED backend. They test your
code. Guardrail 5 is different in one respect and identical in spirit:
it runs regardless of config.DECISION_MODE, and it is what makes
DECISION_MODE == "model" safe to run at all - see config.py.

MAKE THE STOP LOUD. A cap that silently returns an empty answer is
worse than the loop it prevented: it turns a visible cost problem into
an invisible correctness problem. Every stop below records WHY.
====================================================================
"""


class GuardrailStop(Exception):
    """Raised when the code layer halts a run. Carries the reason so the
    decision record can say what stopped it and at which turn."""

    def __init__(self, reason, detail=""):
        self.reason = reason
        self.detail = detail
        super().__init__("%s: %s" % (reason, detail) if detail else reason)


class Guardrails:
    """One instance per run. Never share one between cases - a shared
    instance leaks state and D4 requires every case to start clean."""

    def __init__(self, max_turns, max_tokens, autonomy):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.autonomy = autonomy
        self.seen_actions = set()     # for de-duplication
        self.fired = []               # every guardrail event, for the record

    # ---- 1 · step cap -----------------------------------------------
    def check_turns(self, turn):
        if turn > self.max_turns:
            self._fire("step_cap", "reached %d turns" % self.max_turns)
            raise GuardrailStop("step_cap",
                                "hit the %d-turn cap without a conclusion"
                                % self.max_turns)

    # ---- 2 · budget ceiling -----------------------------------------
    def check_budget(self, tokens_so_far):
        if tokens_so_far > self.max_tokens:
            self._fire("budget_ceiling", "%d tokens" % tokens_so_far)
            raise GuardrailStop("budget_ceiling",
                                "spent %d tokens, ceiling is %d"
                                % (tokens_so_far, self.max_tokens))

    # ---- 3 · action de-duplication ----------------------------------
    def check_duplicate(self, tool, args):
        """A loop has no memory of its own actions unless you give it one.

        This IS that memory. Class 4's loop failure was exactly this
        guard deleted: 8 turns, no answer, 1.6x the cost, and NO
        exception raised. It did not crash. It burned money in a circle.
        """
        signature = (tool, repr(sorted(args.items())))
        if signature in self.seen_actions:
            self._fire("duplicate_action", "%s repeated" % tool)
            raise GuardrailStop("duplicate_action",
                                "%s called again with identical arguments "
                                "- the loop is not progressing" % tool)
        self.seen_actions.add(signature)

    # ---- 4 · autonomy gate ------------------------------------------
    def gate(self, action_name, payload, approve=None):
        """Called ONLY in front of the irreversible step.

        Note where this sits: in front of the ACTION, not in front of the
        agent. An agent gated as a whole is not an agent, it is a form.

        `approve` is a callable the harness supplies. On the scripted
        backend it auto-approves so the run is deterministic - and the
        record still shows the gate was passed, which is what a marker
        checks for.
        """
        if self.autonomy == "act":
            self._fire("gate_passed", "%s (autonomy=act)" % action_name)
            return True
        if self.autonomy == "suggest":
            self._fire("gate_held", "%s (autonomy=suggest)" % action_name)
            return False
        # confirm
        ok = bool(approve and approve(action_name, payload))
        self._fire("gate_%s" % ("passed" if ok else "held"),
                   "%s (autonomy=confirm)" % action_name)
        return ok

    # ---- 5 · route consistency ---------------------------------------
    def check_route_consistency(self, claimed_decision, resolved_decision):
        """Called right before the gated action fires, in BOTH decision
        modes, always - see config.DECISION_MODE.

        `resolved_decision` comes from tools.resolve_routing(), computed
        fresh from the same facts the agent had, regardless of whether the
        agent ever saw that computation. `claimed_decision` is "book" - the
        agent is about to call book_slot, which is itself the claim.

        A hostile instruction in the referral's free text can talk a MODEL
        into concluding "book". It cannot make resolve_routing agree. This
        is the actual backstop, not the model's own good behaviour.

        In DECISION_MODE == "rules" this should NEVER fire - if it does,
        the bug is in resolve_routing or in how its result was handed to
        the agent, not in the model. Worth its own eval case either way.
        """
        if resolved_decision != claimed_decision:
            self._fire("route_mismatch",
                       "agent proceeded to %r but the routing table "
                       "resolves to %r" % (claimed_decision, resolved_decision))
            raise GuardrailStop(
                "route_mismatch",
                "the agent's conclusion (%r) does not match what the "
                "protocol data resolves to (%r) - refusing the irreversible "
                "step" % (claimed_decision, resolved_decision))

    def note_mismatch(self, claimed_decision, resolved_decision):
        """A non-blocking version of the same check, for the ask/escalate
        paths. Getting these wrong is not dangerous the way a wrong
        booking is - the asymmetry the brief asks you to design around -
        so this only LOGS a mismatch instead of stopping the run. It is
        what lets you measure, per config.DECISION_MODE, how often the
        model's own reasoning would have disagreed with the protocol even
        when it never reached the point of booking."""
        if resolved_decision is not None and resolved_decision != claimed_decision:
            self._fire("route_mismatch_nonblocking",
                       "agent concluded %r, routing table resolves to %r"
                       % (claimed_decision, resolved_decision))

    # ---- bookkeeping ------------------------------------------------
    def _fire(self, kind, detail):
        self.fired.append({"guardrail": kind, "detail": detail})
