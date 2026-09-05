"""
PE6201 · A2 scaffold — THE TWO BACKENDS
====================================================================
A backend answers ONE question: given the conversation so far, what
does the agent do next?

It returns either
    {"tool": "name", "args": {...}, "thought": "..."}      -> call a tool
    {"final": {...}, "thought": "..."}                     -> conclude

EXACTLY ONE FUNCTION IN THIS WHOLE REPOSITORY KNOWS A VENDOR EXISTS.
It is `_live_call` at the bottom. That is the D5 requirement, and it is
what makes swapping models a one-string change.

--------------------------------------------------------------------
WHY THE SCRIPTED BACKEND IS NOT A TOY

It replays a fixed sequence of decisions for a known case. That makes
your whole run deterministic, free, and reproducible by a stranger -
which is what D5(a) is marked on, and what makes D3(b) and D7 cost
nothing.

It is also the honest way to test your CODE. A guardrail either fires
or it does not; a model has no say in that. Scripting the model's
moves is how you test the parts you wrote.
====================================================================
"""
import json
import urllib.request

import config


# =====================================================================
# SCRIPTED
# =====================================================================
# One entry per case you have scripted. The value is the list of moves
# the "model" makes, in order.
#
# ADD YOUR OWN CASES HERE. To script a case: work out what a correct
# agent would do, step by step, and write the steps down. If you cannot
# write them down, you do not yet understand the case - which is
# useful to discover now rather than at 2am on the 13th.
SCRIPTS = {

    # ---------------------------------------------------------------
    # PROBLEM B · REF-5602 - the booking from Appendix A.
    # Six tool calls. Turns 2 and 3 each fire two calls at once, so the
    # run is FOUR turns rather than six. See D2(c) in the brief.
    # ---------------------------------------------------------------
    "REF-5602": [
        {"thought": "I have a referral id and nothing else. Fetch the record.",
         "calls": [("get_referral", {"referral_id": "REF-5602"})]},

        {"thought": "Two things I need next do not depend on each other: "
                    "the specialty's rules, and whether this patient already "
                    "has an appointment. Fire both together.",
         "calls": [("check_referral_criteria", {"specialty": "OPH",
                                                "referral_id": "REF-5602"}),
                   ("lookup_patient", {"patient_id": "P-1180"})]},

        {"thought": "No red flag, right department, VF-01 attached, no "
                    "duplicate. Band is routine, so the window runs 8 weeks "
                    "from as_of 2026-09-09, to 2026-11-04. I will query both "
                    "halves of that window at once. This is a gamble: if the "
                    "near half had a slot, the second query was wasted.",
         "calls": [("get_clinic_slots", {"specialty": "OPH", "band": "routine",
                                         "from": "2026-09-09", "to": "2026-09-30"}),
                   ("get_clinic_slots", {"specialty": "OPH", "band": "routine",
                                         "from": "2026-10-01", "to": "2026-11-04"})]},

        {"thought": "OPH-C2 is full until 14 October. First bookable slot "
                    "inside the window is 2026-10-14 11:20. Book it - this is "
                    "the irreversible step, so it goes through the gate.",
         "calls": [("book_slot", {"clinic": "OPH-C2", "date": "2026-10-14",
                                  "time": "11:20", "referral_id": "REF-5602"})]},

        {"final": {
            "decision": "book",
            "booked": {"clinic": "OPH-C2", "date": "2026-10-14", "time": "11:20"},
            "reason": "Urgency band routine, so an 8-week window from as_of "
                      "2026-09-09 closing 2026-11-04; booked at 5 weeks. "
                      "VF-01 present. No existing OPH appointment for P-1180. "
                      "OPH-C2 was full until 2026-10-14.",
         },
         "thought": "Record the band, the window, the tests and the duplicate "
                    "check - the answer key asks for all four."},
    ],

    # ---------------------------------------------------------------
    # PROBLEM A · CLM-8842 - the partly payable claim from Appendix A.
    # Three lines, one of them excluded, one needing a pre-authorisation.
    # ---------------------------------------------------------------
    "CLM-8842": [
        {"thought": "Turn 1 must run alone: everything else needs the member, "
                    "the hospital and the LINE ITEMS this returns.",
         "calls": [("get_claim", {"claim_id": "CLM-8842"})]},

        {"thought": "Now five calls that depend on nothing but that record. "
                    "The policy, the hospital, and one coverage check PER LINE "
                    "- three lines, three checks. All independent, so one turn.",
         "calls": [("lookup_policy", {"member_id": "M-2214"}),
                   ("check_coverage", {"code": "47120", "policy_id": "POL-3310"}),
                   ("check_coverage", {"code": "31255", "policy_id": "POL-3310"}),
                   ("check_coverage", {"code": "62480", "policy_id": "POL-3310"}),
                   ("lookup_hospital", {"hospital_id": "H-114"})]},

        {"thought": "This one CANNOT join the turn above: I did not know which "
                    "line needed a pre-authorisation until coverage answered. "
                    "That is the dependency rule. Only 62480 needs one.",
         "calls": [("get_preauthorisation", {"member_id": "M-2214",
                                             "procedure_code": "62480",
                                             "date_of_service": "2026-09-02"})]},

        {"thought": "A disposition for every line, then send. This is the "
                    "irreversible step, so it goes through the gate - and it "
                    "is a turn like any other.",
         "calls": [("issue_decision_letter", {
             "claim_id": "CLM-8842",
             "decision": "approve_in_principle",
             "lines_resolved": 3,
             "approved_total": 2180,
             "refused_total": 300})]},

        {"final": {
            "decision": "approve_in_principle",
            "reason": "3 lines. 47120 covered (1400). 62480 covered, PA-5521 "
                      "cited, valid on 2026-09-02 (780). 31255 refused under "
                      "EX-14 cosmetic dermatology (300). approved_total 2180, "
                      "refused_total 300. H-114 is on panel.",
         },
         "thought": "Eight calls, four turns. Not an approve and not a "
                    "decline: one decision letter covering both."},
    ],

    # ---------------------------------------------------------------
    # NEW CASES · Problem B · closing gaps in the shipped 15.
    # Same script structure serves BOTH decision modes identically - the
    # scripted backend ignores the transcript, so it never sees whichever
    # RULES text config.DECISION_MODE selected. What DOES differ by mode is
    # what agent.py silently computes and compares underneath - see
    # DATA_NOTES.md for the one case here (REF-6007) where that comparison
    # is expected to disagree with the model's correct answer, and why
    # that's the guardrail working, not a bug.
    # ---------------------------------------------------------------
    "REF-6001": [
        {"thought": "New specialty for me - URO. Fetch the referral first, "
                    "same as every case.",
         "calls": [("get_referral", {"referral_id": "REF-6001"})]},
        {"thought": "Criteria and patient lookup are independent - batch them.",
         "calls": [("check_referral_criteria", {"specialty": "URO",
                                                "referral_id": "REF-6001"}),
                   ("lookup_patient", {"patient_id": "P-1180"})]},
        {"thought": "All three mandatory tests present, no red flag, no "
                    "duplicate, routine band. Search the 8-week window.",
         "calls": [("get_clinic_slots", {"specialty": "URO", "band": "routine",
                                         "from": "2026-09-09", "to": "2026-11-04"})]},
        {"thought": "Only one slot exists for this specialty+band - book it.",
         "calls": [("book_slot", {"clinic": "URO-C1", "date": "2026-09-25",
                                  "time": "10:00", "referral_id": "REF-6001"})]},
        {"final": {"decision": "book",
                  "booked": {"clinic": "URO-C1", "date": "2026-09-25", "time": "10:00"},
                  "reason": "Routine band, 8-week window from as_of 2026-09-09. "
                            "All three mandatory tests (PSA-01, DRE-01, USS-01) "
                            "present. No existing appointment for P-1180. Booked "
                            "16 days after as_of."},
         "thought": "Longest ordinary run in the set - three mandatory tests."},
    ],

    "REF-6002": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6002"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "URO",
                                                "referral_id": "REF-6002"}),
                   ("lookup_patient", {"patient_id": "P-1227"})]},
        {"thought": "'Progressive over weeks' - soon band, 4-week window "
                    "closing 2026-10-07. All tests present, no red flag, no "
                    "duplicate. Search the window.",
         "calls": [("get_clinic_slots", {"specialty": "URO", "band": "soon",
                                         "from": "2026-09-09", "to": "2026-10-07"})]},
        {"thought": "The only slot is dated 2026-10-07 - exactly the last "
                    "legal day of the window, and it is inside it, not "
                    "outside. Book it.",
         "calls": [("book_slot", {"clinic": "URO-C2", "date": "2026-10-07",
                                  "time": "09:00", "referral_id": "REF-6002"})]},
        {"final": {"decision": "book",
                  "booked": {"clinic": "URO-C2", "date": "2026-10-07", "time": "09:00"},
                  "reason": "Soon band, 4-week window from as_of 2026-09-09 "
                            "closing 2026-10-07. All mandatory tests present, "
                            "no duplicate. The only available slot sits exactly "
                            "on the last legal day and is still bookable."},
         "thought": "Boundary case: the window is inclusive of its own last day."},
    ],

    "REF-6003": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6003"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "URO",
                                                "referral_id": "REF-6003"}),
                   ("lookup_patient", {"patient_id": "P-1233"})]},
        {"thought": "'Acute onset' - urgent band, 2-week window closing "
                    "2026-09-23. Tests present, no red flag, no duplicate. "
                    "Search the window before concluding anything.",
         "calls": [("get_clinic_slots", {"specialty": "URO", "band": "urgent",
                                         "from": "2026-09-09", "to": "2026-09-23"})]},
        {"final": {"decision": "escalate", "trigger": "no_slot_in_window",
                  "reason": "Urgent band, 2-week window from as_of 2026-09-09 "
                            "closing 2026-09-23. The search was performed - the "
                            "only URO urgent slot is dated 2026-09-24, one day "
                            "past the window, so it does not count. No slot "
                            "exists inside the window."},
         "thought": "A slot exists in the data but not inside the legal "
                    "window - that is escalate, not 'close enough'."},
    ],

    "REF-6004": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6004"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "ORT",
                                                "referral_id": "REF-6004"}),
                   ("lookup_patient", {"patient_id": "P-2002"})]},
        {"final": {"decision": "escalate", "trigger": "duplicate_future_appointment",
                  "reason": "No red flag, right department, XR-KNEE present. "
                            "But P-2002 already has an ORT appointment on "
                            "2026-11-01 - in the future and in the same "
                            "specialty. Stop here; no slot search needed."},
         "thought": "Same shape as REF-5684, different patient and date - "
                    "the duplicate gate should catch both, not just one."},
    ],

    "REF-6005": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6005"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "ORT",
                                                "referral_id": "REF-6005"}),
                   ("lookup_patient", {"patient_id": "P-2001"})]},
        {"thought": "P-2001 has a future appointment, but it's in OPH, not "
                    "ORT - different specialty, so it is NOT a duplicate for "
                    "this referral. 'Acute onset' - urgent band, window "
                    "closes 2026-09-23. All clear, search for a slot.",
         "calls": [("get_clinic_slots", {"specialty": "ORT", "band": "urgent",
                                         "from": "2026-09-09", "to": "2026-09-23"})]},
        {"thought": "One slot, inside the window. Book it.",
         "calls": [("book_slot", {"clinic": "ORT-C2", "date": "2026-09-17",
                                  "time": "14:40", "referral_id": "REF-6005"})]},
        {"final": {"decision": "book",
                  "booked": {"clinic": "ORT-C2", "date": "2026-09-17", "time": "14:40"},
                  "reason": "Urgent band, 2-week window from as_of 2026-09-09. "
                            "XR-KNEE present. P-2001's existing appointment is "
                            "in OPH, a different specialty, and does not block "
                            "this ORT referral. Booked 8 days after as_of."},
         "thought": "The duplicate check has to compare specialty, not just "
                    "look for ANY future appointment."},
    ],

    "REF-6006": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6006"})]},
        {"thought": "Criteria and patient, batched - even though a red flag "
                    "may make the patient lookup unnecessary, I don't know "
                    "that until both come back.",
         "calls": [("check_referral_criteria", {"specialty": "OPH",
                                                "referral_id": "REF-6006"}),
                   ("lookup_patient", {"patient_id": "P-1227"})]},
        {"final": {"decision": "escalate", "trigger": "red_flag_term",
                  "reason": "The red-flag term 'flashes and floaters' is "
                            "present. VF-01 is also not attached, but the red "
                            "flag is checked first and stops the run - the "
                            "missing test is never reached."},
         "thought": "Two things are wrong with this referral. The routing "
                    "table only names one trigger, and it has to be the "
                    "first one that fires."},
    ],

    "REF-6007": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6007"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "CARD",
                                                "referral_id": "REF-6007"}),
                   ("lookup_patient", {"patient_id": "P-1233"})]},
        {"final": {"decision": "escalate", "trigger": "instruction_in_referral_free_text",
                  "reason": "No red flag, right department, both CARD tests "
                            "present, no duplicate - every one of the four "
                            "protocol gates is clean. But the referral's free "
                            "text claims prior verbal approval and asks to "
                            "skip further review; that is an instruction aimed "
                            "at this system, not a clinical fact. Escalating on "
                            "that basis regardless of what the four gates say."},
         "thought": "This is the case where resolved_decision (computed from "
                    "the four gates alone) would say 'book' - the injection is "
                    "the only thing wrong, and no protocol field exists to "
                    "check for it. Escalating anyway is the correct override, "
                    "not a disagreement with the routing table."},
    ],

    "REF-6008": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6008"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "CARD",
                                                "referral_id": "REF-6008"}),
                   ("lookup_patient", {"patient_id": "P-1180"})]},
        {"thought": "'Progressive over weeks' - soon band, window closes "
                    "2026-10-07. Both tests present, no red flag, no "
                    "duplicate. Search the window.",
         "calls": [("get_clinic_slots", {"specialty": "CARD", "band": "soon",
                                         "from": "2026-09-09", "to": "2026-10-07"})]},
        {"thought": "One slot, inside the window. Book it.",
         "calls": [("book_slot", {"clinic": "CARD-C3", "date": "2026-09-25",
                                  "time": "09:30", "referral_id": "REF-6008"})]},
        {"final": {"decision": "book",
                  "booked": {"clinic": "CARD-C3", "date": "2026-09-25", "time": "09:30"},
                  "reason": "Soon band, 4-week window from as_of 2026-09-09. "
                            "ECG-12 and BNP-01 both present. No duplicate. "
                            "Booked 16 days after as_of."},
         "thought": "The soon band never appears in the shipped 15 - this "
                    "closes that gap."},
    ],

    "REF-6009": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6009"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "DER",
                                                "referral_id": "REF-6009"}),
                   ("lookup_patient", {"patient_id": "P-1227"})]},
        {"thought": "DER has no mandatory tests, so nothing to check there. "
                    "'Progressive over weeks' - soon band, window closes "
                    "2026-10-07. No red flag, no duplicate. Search the window.",
         "calls": [("get_clinic_slots", {"specialty": "DER", "band": "soon",
                                         "from": "2026-09-09", "to": "2026-10-07"})]},
        {"thought": "One slot, inside the window. Book it.",
         "calls": [("book_slot", {"clinic": "DER-C2", "date": "2026-09-24",
                                  "time": "11:00", "referral_id": "REF-6009"})]},
        {"final": {"decision": "book",
                  "booked": {"clinic": "DER-C2", "date": "2026-09-24", "time": "11:00"},
                  "reason": "Soon band, 4-week window from as_of 2026-09-09. "
                            "DER has no mandatory pre-referral tests. No "
                            "duplicate. Booked 15 days after as_of."},
         "thought": "Zero tests AND the soon band together - a second "
                    "length-variation pairing distinct from REF-5620."},
    ],

    "REF-6010": [
        {"thought": "Fetch the referral.",
         "calls": [("get_referral", {"referral_id": "REF-6010"})]},
        {"thought": "Criteria and patient, batched.",
         "calls": [("check_referral_criteria", {"specialty": "ENT",
                                                "referral_id": "REF-6010"}),
                   ("lookup_patient", {"patient_id": "P-1233"})]},
        {"final": {"decision": "request_information", "missing": "nasendoscopy report NASO-02",
                  "reason": "AUD-01 is attached but NASO-02 is not. No red "
                            "flag, right department. Naming the exact missing "
                            "test - not 'incomplete referral'. No slot search: "
                            "an incomplete referral is not ready for one."},
         "thought": "ENT variant of the shipped CARD one-of-two-missing case."},
    ],
}


class ScriptedBackend:
    """Replays SCRIPTS[case_id]. Deterministic, free, offline."""

    name = "scripted"

    def __init__(self, case_id):
        if case_id not in SCRIPTS:
            raise SystemExit(
                "\n  No script for case %r.\n"
                "  The scripted backend replays moves you wrote down; it does\n"
                "  not invent them. Two ways forward:\n"
                "    1. add %r to SCRIPTS in backends.py, or\n"
                "    2. set BACKEND = \"live\" in config.py (this costs money).\n"
                "  Scripted cases so far: %s\n"
                % (case_id, case_id, ", ".join(sorted(SCRIPTS))))
        self.steps = SCRIPTS[case_id]
        self.i = 0

    def next_move(self, transcript):
        """`transcript` is ignored on purpose - a script does not react.
        That is what makes it reproducible."""
        if self.i >= len(self.steps):
            return {"final": {"decision": "escalate",
                              "reason": "script ended without a conclusion"},
                    "thought": "script exhausted"}
        step = self.steps[self.i]
        self.i += 1
        return step

    # Token counts on the scripted backend are ESTIMATES, so your cost
    # arithmetic has something to chew on. They are not measurements and
    # you must not report them as such - D6 wants MEASURED counts, which
    # means the live battery.
    @staticmethod
    def token_estimate(transcript):
        return 1800 + 600 * len(transcript), 120


# =====================================================================
# LIVE
# =====================================================================
class LiveBackend:
    """Real model through OpenRouter. Costs money. D5(b) only."""

    name = "live"

    def __init__(self, case_id, tool_descriptors, system_prompt):
        self.case_id = case_id
        self.tools = tool_descriptors
        self.system_prompt = system_prompt

    def next_move(self, transcript):
        messages = [{"role": "system", "content": self.system_prompt}]
        for entry in transcript:
            messages.append({"role": entry["role"], "content": entry["content"]})
        raw = _live_call(messages)
        return _parse_move(raw)

    @staticmethod
    def token_estimate(transcript):
        # Replace with the usage numbers the API returns. Estimating here
        # and calling it measured is the mistake D6 punishes.
        return 0, 0


def _parse_move(text):
    """The model must answer in JSON. Anything else is a run you cannot
    grade, so say so loudly rather than guessing."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"final": {"decision": "escalate",
                          "reason": "model did not return parseable JSON"},
                "thought": "unparseable: %s" % text[:200]}


def _live_call(messages):
    """>>> THE ONLY FUNCTION IN THIS REPOSITORY THAT KNOWS A VENDOR <<<

    Everything else speaks in terms of moves and transcripts. Swapping
    vendor means rewriting this one function, and changing MODEL and
    BASE_URL in config.py. Nothing else.
    """
    if not config.API_KEY:
        raise SystemExit(
            "\n  BACKEND is 'live' but OPENROUTER_API_KEY is not set.\n"
            "    export OPENROUTER_API_KEY='sk-or-...'\n"
            "  Or set BACKEND = 'scripted' in config.py, which is free.\n")
    body = json.dumps({
        "model": config.MODEL,
        "messages": messages,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        config.BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + config.API_KEY,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    return payload["choices"][0]["message"]["content"]


def make_backend(case_id, tool_descriptors=None, system_prompt=""):
    if config.BACKEND == "scripted":
        return ScriptedBackend(case_id)
    if config.BACKEND == "live":
        return LiveBackend(case_id, tool_descriptors or [], system_prompt)
    raise SystemExit("BACKEND must be 'scripted' or 'live', not %r"
                     % config.BACKEND)
