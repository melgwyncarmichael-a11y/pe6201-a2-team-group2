"""
PE6201 · A2 scaffold — THE TOOL LAYER  (D2)
====================================================================
A tool reads ONE thing from the reference data and returns ONE fact.

THE NAMES BELOW ARE OURS, NOT YOURS. Appendix A says so and so does the
brief: these describe work that has to happen, not an interface you must
implement. Rename, re-argument, merge, split, add. What you cannot do is
change the ROUTING RULE or the GATED ACTION - the answer key is written
against those.

--------------------------------------------------------------------
HOW TO READ THIS FILE

Every tool carries the same comment block, and it is worth copying the
shape for your own tools:

    WHAT IT DOES   one sentence, in domain language
    READS          which JSON file(s) it touches
    RETURNS        the exact shape that comes back
    RETURNS NONE   when, AND WHAT THAT MEANS - these are different
    WATCH OUT      the mistake this tool exists to prevent

The fourth line is the one that separates a tool from a lookup. "Returns
None" is a fact about Python. "Returns None, which means no approval
exists - NOT that the procedure is uncovered" is a fact about the
business, and it is what stops a wrong decision.

--------------------------------------------------------------------
THE SIX-FIELD DESCRIPTOR (D2b)

EVERY tool below has one, at the bottom of this file. THEY ARE NOT
DECORATION - `prompt.build_system_prompt()` assembles them into the text
the model is actually sent, so editing one changes what the agent sees.

    python3 run_eval.py --prompt      shows the exact text, and its size

That is what makes D2(b) measurable. Rewrite the descriptors, print the
prompt, and the diff is precisely what you are claiming to have
measured. The v1 you compare against should be a genuinely worse version
you wrote - and note the prompt is resent EVERY TURN, so a longer
descriptor has to earn its length on every turn of every run.

--------------------------------------------------------------------
POKA-YOKE: make the wrong call impossible rather than documented.
Two examples below - `get_clinic_slots` demands a band so you cannot
accidentally book an urgent patient into a routine slot, and
`check_coverage` demands a policy_id so you cannot check coverage
against no policy at all.
====================================================================
"""
import json
import os

import config

_CACHE = {}


def _load(problem, table):
    """Read one JSON file, once, and keep it in memory.

    WHAT IT DOES   internal helper - the tools below read through it.
    WATCH OUT      the agent NEVER calls this and never sees these files.
                   It asks a tool a question and gets one answer back. An
                   agent handed all the data in its first prompt is making
                   a single call, not running a loop - which is exactly
                   what D0(a) asks you to defend.

    The cache is per-process, so a run never re-reads a file. It also
    means editing a JSON file mid-session has no effect until you
    restart - if the data looks stale, that is why.
    """
    key = (problem, table)
    if key not in _CACHE:
        path = os.path.join(config.data_root(), "data_%s" % problem,
                            "%s.json" % table)
        with open(path, encoding="utf-8") as fh:
            _CACHE[key] = json.load(fh)
    return _CACHE[key]


# =====================================================================
# PROBLEM B · outpatient referral coordination
# =====================================================================

def get_referral(referral_id):
    """Fetch the one referral the agent has been asked to handle.

    WHAT IT DOES   turns an id into the actual record: patient, specialty,
                   date, tests attached, and the GP's free-text summary.
    READS          data_B/referrals.json
    RETURNS        the referral row, or None
    RETURNS NONE   when no referral has that id. That is a BROKEN CASE,
                   not a business outcome - the agent was handed an id
                   that resolves to nothing. check_my_data.py exists to
                   catch this before a run ever happens.
    WATCH OUT      this is almost always turn 1 and it must run ALONE.
                   Everything else needs the patient_id and specialty it
                   returns, so nothing can be parallelised with it.

    Note what is NOT in the row it returns: no urgency, no red-flag
    verdict, no slot, no rule. Every one of those has to be fetched.
    That is what makes this an agent loop rather than one big call.
    """
    for r in _load("B", "referrals"):
        if r["referral_id"] == referral_id:
            return r
    return None


def lookup_patient(patient_id):
    """Who the patient is, what they already have booked, and how to
    reach them.

    WHAT IT DOES   answers the duplicate question and the contact question
                   in one call.
    READS          data_B/patients.json AND data_B/contacts.json
    RETURNS        {"patient": {...}, "contact": {...}}
    RETURNS NONE   when the patient_id matches nobody - again a broken
                   case, not an outcome.
    WATCH OUT      contacts and patients share the SAME KEY. Reading
                   contacts "through" patients would be a two-hop chain
                   and an extra turn for nothing. Both are fetched here
                   for that reason.

    THE DUPLICATE RULE, because this is where teams lose the case:
    `patient["existing_appointments"]` is a duplicate only when BOTH are
    true - the same specialty AND a date in the future, measured from
    as_of(). A past appointment in the same specialty is NOT a duplicate;
    the patient was seen and has been referred again. An empty list is
    normal and means nothing is booked.

    This tool does not decide that for you. It hands you the appointments
    and the decision is the agent's - which is deliberate, because the
    decision is what D4 grades.
    """
    p = next((x for x in _load("B", "patients")
              if x["patient_id"] == patient_id), None)
    if p is None:
        return None
    c = next((x for x in _load("B", "contacts")
              if x["patient_id"] == patient_id), None)
    return {"patient": p, "contact": c}


def check_referral_criteria(specialty, referral_id):
    """Run the department's protocol against this referral's free text.

    WHAT IT DOES   answers the four questions that can each end the run,
                   plus the urgency band, in one call.
    READS          data_B/specialties.json, data_B/urgency_bands.json,
                   and the referral itself
    RETURNS        {"red_flag_term":   the matched phrase, or None
                    "right_department": True/False
                    "missing_tests":   list of mandatory tests NOT attached
                    "band":            "urgent" | "soon" | "routine"
                    "window_weeks":    2 | 4 | 8}
    RETURNS NONE   when the referral or the specialty does not exist.
    WATCH OUT      THIS TOOL DECIDES NOTHING. It reports five facts. The
                   agent decides what they mean, and the ORDER matters:

                       red_flag_term is not None   -> ESCALATE, stop
                       right_department is False   -> ESCALATE, stop
                       missing_tests is non-empty  -> REQUEST INFO, stop
                       otherwise                   -> carry on to slots

                   An agent that queries a slot after finding a red flag
                   has failed the case even if it never books.

    WHY THIS IS ONE TOOL AND NOT FOUR - a design choice worth arguing
    with. The four questions are always asked, always in this order, and
    each can end the run. Splitting them into four tools would invite an
    agent to ask them out of order or skip one, and would cost three
    extra turns for no information. The cost is that this tool is doing
    four things, which is usually bad design.
    D2(a) marks your REASONING about the tool set, not ours - so if you
    split it, say why, and you are on perfectly good ground.

    HOW THE THREE TEXT CHECKS WORK, so you can see how crude they are:
      - red flags   substring match of the specialty's red_flag_terms
      - department  substring match of the specialty's `treats` words
      - band        first urgency band whose trigger_terms appear;
                    NO TRIGGER FOUND MEANS ROUTINE, which is the default
                    and not an error
    Substring matching is fragile on purpose. Your prompt-injection
    cases will attack exactly this, and improving it is fair game - just
    do not change the PROTOCOL, only how you detect it.
    """
    ref = get_referral(referral_id)
    spec = next((s for s in _load("B", "specialties")
                 if s["code"] == specialty), None)
    if ref is None or spec is None:
        return None
    text = ref["clinical_summary"].lower()

    red = next((t for t in spec["red_flag_terms"] if t.lower() in text), None)
    right_department = any(w.lower() in text for w in spec["treats"])
    attached = set(ref.get("tests_attached", []))
    missing = [t for t in spec["mandatory_tests"] if t["code"] not in attached]

    band, weeks = "routine", 8            # <- routine is the DEFAULT
    for b in _load("B", "urgency_bands"):
        if any(t.lower() in text for t in b["trigger_terms"]):
            band, weeks = b["band"], b["window_weeks"]
            break

    return {"red_flag_term": red,
            "right_department": right_department,
            "missing_tests": missing,
            "band": band,
            "window_weeks": weeks}


def get_clinic_slots(specialty, band, **window):
    """Find appointment slots that exist AND are free AND are legal.

    WHAT IT DOES   three filters at once: right department, right band,
                   inside the window, with a place left.
    READS          data_B/clinic_slots.json
    RETURNS        list of {clinic, specialty, band, date, time,
                   capacity_remaining} - possibly empty
    RETURNS EMPTY  when nothing is free in that window. EMPTY IS AN
                   ANSWER, not a failure: it means ESCALATE with trigger
                   `no_slot_in_window`. It does NOT mean widen the
                   window, and it does NOT mean drop to another band.
    WATCH OUT      capacity_remaining == 0 means the slot EXISTS AND IS
                   FULL. That is a different fact from the slot not
                   existing, and this tool filters those rows out for
                   you - so an empty list can mean either. If your
                   record needs to distinguish them, read the file.

    POKA-YOKE: `band` IS A REQUIRED ARGUMENT, and this is the clearest
    example in the scaffold of designing an interface so the wrong call
    cannot be made.

    On the shipped data, REF-5602 is a routine referral with an 8-week
    window closing 2026-11-04. THREE slots sit earlier inside that window
    with capacity free - OPH-C1 on 09-15 and 09-22 (urgent) and OPH-C3 on
    09-29 (soon). A team filtering by date alone books one of them and
    fails the case. Only the band excludes them, and making band an
    argument rather than an optional filter is what makes forgetting it
    impossible rather than merely documented.

    The window is passed as **kwargs so `from` can be used as a name -
    it is a Python keyword and cannot be a normal parameter. That is a
    small ugliness bought deliberately, to keep the domain word.
    """
    lo = window.get("from", "0000-00-00")
    hi = window.get("to", "9999-99-99")
    return [s for s in _load("B", "clinic_slots")
            if s["specialty"] == specialty
            and s["band"] == band
            and lo <= s["date"] <= hi
            and s["capacity_remaining"] > 0]


def book_slot(clinic, date, time, referral_id):
    """>>> THE IRREVERSIBLE STEP FOR PROBLEM B <<<

    WHAT IT DOES   commits the appointment. A patient is now expected at
                   a clinic on a date.
    READS          nothing - it WRITES, conceptually
    RETURNS        a confirmation carrying everything the record needs
    WATCH OUT      this is the ONE call in Problem B that cannot be taken
                   back. Every other tool can be re-run harmlessly.

    THIS IS WHAT THE AUTONOMY GATE SITS IN FRONT OF - see guardrails.py
    and the GATED_ACTION table below. Note WHERE the gate goes: in front
    of THIS ACTION, not in front of the agent as a whole. An agent gated
    as a whole is not an agent, it is a form, and D3(a) asks you to
    defend the placement.

    In this scaffold it returns a dict rather than touching anything -
    there is no real booking system. Your evaluation runs would be
    unrepeatable if there were, which is worth noticing: an agent that
    genuinely changes the world is much harder to test, and that is a
    real cost of autonomy, not a detail of this exercise.
    """
    return {"booked": True, "clinic": clinic, "date": date,
            "time": time, "referral_id": referral_id}


def resolve_routing(specialty, criteria, patient_lookup, as_of_date):
    """>>> APPENDIX A'S ROUTING TABLE, WRITTEN AS CODE <<<

    WHAT IT DOES   applies the four gates, in the fixed order, to facts the
                   OTHER tools already fetched. It does not look anything up
                   itself - everything it needs is passed in.
    READS          nothing. Pure function over its arguments.
    RETURNS        {"resolved_decision": "book" | "request_information" |
                    "escalate", "trigger": str or None, "missing": str or
                    None}. "book" here means "all four gates cleared, go
                    look for a slot" - a slot still has to exist inside the
                    window before anything is actually booked.
    FAILS WHEN     never. It is arithmetic over data already in hand.
    IRREVERSIBLE?  No. This never calls book_slot and never touches it.

    THIS EXISTS BECAUSE config.DECISION_MODE == "rules" MEANS THIS FUNCTION
    resolves the decision instead of the model's own reasoning. But it also
    runs when DECISION_MODE == "model" - silently, never shown to the model
    - purely so guardrails.check_route_consistency can compare what the
    model concluded against what the protocol data actually says. See
    config.py for the full argument for why both modes exist.

    WATCH OUT      this needs `specialty` as its own argument because
                   check_referral_criteria's return does not echo back which
                   specialty was checked - and the duplicate gate has to
                   compare AGAINST that specialty, not re-derive it.
    """
    if criteria.get("red_flag_term"):
        return {"resolved_decision": "escalate",
                "trigger": "red_flag_term", "missing": None}

    if not criteria.get("right_department"):
        return {"resolved_decision": "escalate",
                "trigger": "specialty_mismatch", "missing": None}

    missing_tests = criteria.get("missing_tests") or []
    if missing_tests:
        return {"resolved_decision": "request_information",
                "trigger": None, "missing": missing_tests[0]["name"]}

    appointments = (patient_lookup.get("patient") or {}).get(
        "existing_appointments") or []
    for appt in appointments:
        if appt["specialty"] == specialty and appt["date"] > as_of_date:
            return {"resolved_decision": "escalate",
                    "trigger": "duplicate_future_appointment", "missing": None}

    return {"resolved_decision": "book", "trigger": None, "missing": None}


def as_of():
    """The clock for Problem B.

    WHAT IT DOES   returns the single date every urgency window is
                   measured FROM.
    READS          data_B/as_of.json
    RETURNS        a date string, e.g. "2026-09-09"
    WATCH OUT      windows are counted from THIS, not from the referral's
                   `date_received`. They happen to be equal for some
                   shipped referrals, which is exactly the sort of
                   coincidence that hides a bug until a case where they
                   differ.

    Move this date and every booking case in the answer key silently
    becomes wrong. The data guide says leave it alone, and it means it.
    """
    return _load("B", "as_of")["as_of"]


# =====================================================================
# PROBLEM A · health-insurance claim first response
# =====================================================================

def get_claim(claim_id):
    """Fetch the one claim the agent has been asked to decide.

    WHAT IT DOES   turns an id into the record: member, hospital, date,
                   attached documents, the member's narrative, and the
                   LINE ITEMS.
    READS          data_A/claims.json
    RETURNS        the claim row, or None
    RETURNS NONE   when no claim has that id - a broken case, not an
                   outcome.
    WATCH OUT      `lines` is a LIST. Nine of the fifteen shipped claims
                   have one line; six have two to four. Every line needs
                   its own coverage check and its own disposition, and an
                   agent that checks only the first line quietly approves
                   things it should refuse.

    Like get_referral, this must run ALONE on turn 1 - everything after
    it needs the member, the hospital and the lines it returns. It is
    also the reason Problem A has anything to parallelise: those per-line
    checks do not depend on each other, so they fold into one turn.
    """
    for c in _load("A", "claims"):
        if c["claim_id"] == claim_id:
            return c
    return None


def lookup_policy(member_id):
    """Follow the claim to the money and the rules.

    WHAT IT DOES   claim -> member -> policy, and does the headroom
                   arithmetic for you.
    READS          data_A/members.json AND data_A/policies.json
    RETURNS        {"member": {...}, "policy": {...}, "remaining": int}
    RETURNS NONE   when the member or their policy does not exist.
    WATCH OUT      `remaining` is annual_limit MINUS used_to_date. The
                   claim total is tested against THAT, not against
                   annual_limit. Testing against the limit is a silent
                   wrong answer on any policy with spend on it.

    THREE SEPARATE REASONS TO REFUSE live in the row this returns, and
    they are easy to conflate:
      1. status == "lapsed"              -> escalate, nothing else matters
      2. date_of_service outside
         start_date .. end_date          -> escalate, even if status is active
      3. lines exceed `remaining`         -> escalate
    Note (2): a policy can say "active" and still not cover the date. The
    shipped data has a claim that tests exactly this.

    The member row itself carries NO decision information - it is a
    bridge. `join_date` in particular is not a coverage date; the
    policy's own dates govern.
    """
    m = next((x for x in _load("A", "members")
              if x["member_id"] == member_id), None)
    if m is None:
        return None
    p = next((x for x in _load("A", "policies")
              if x["policy_id"] == m["policy_id"]), None)
    if p is None:
        return None
    return {"member": m, "policy": p,
            "remaining": p["annual_limit"] - p["used_to_date"]}


def lookup_hospital(hospital_id):
    """Is the hospital inside the insurer's network?

    WHAT IT DOES   one boolean and a name.
    READS          data_A/hospitals.json
    RETURNS        {hospital_id, name, panel, country} or None
    WATCH OUT      panel status does NOT by itself decide the claim. A
                   non-panel hospital means the member paid and is
                   claiming it back rather than the insurer settling
                   directly - so it changes what the record must SAY, not
                   what the decision IS.

    It is still a required call. An agent that never checked cannot
    claim it did, and the decision record is what a marker reads.
    """
    return next((h for h in _load("A", "hospitals")
                 if h["hospital_id"] == hospital_id), None)


def check_coverage(code, policy_id):
    """Is this ONE procedure payable under THIS policy?

    WHAT IT DOES   resolves one line item: what the code means, whether
                   it needed permission first, and whether this product
                   excludes it.
    READS          data_A/procedures.json AND data_A/policies.json
    RETURNS        {"code", "description", "requires_preauth" (bool),
                    "excluded" (bool), "exclusion_rule" (str or None)}
    RETURNS NONE   when the code or the policy does not exist.
    WATCH OUT      CALL THIS ONCE PER LINE. A three-line claim needs
                   three calls - and because they are independent of each
                   other, all three belong in the same turn.

    TWO FIELDS THAT DRIVE EVERYTHING AFTER THIS:

      `requires_preauth` is THE BRANCH. True means go and look for an
      approval; False means do not. This single boolean is why claims
      vary in run length, and an agent that calls get_preauthorisation
      for every line has not read it.

      `excluded` refuses THE LINE, not the claim. Three lines approved
      and one excluded is ONE decision letter covering both - "approve in
      principle" with a disposition per line. Escalating the whole claim
      because one line is excluded is a distinct, and common, failure.
      When excluded, `exclusion_rule` gives you the rule id to cite; the
      record should name it, not merely say "excluded".

    POKA-YOKE: `policy_id` is REQUIRED. Coverage is meaningless without a
    policy, and a tool that let you omit it would cheerfully return an
    answer about nothing at all.
    """
    proc = next((p for p in _load("A", "procedures") if p["code"] == code), None)
    pol = next((p for p in _load("A", "policies")
                if p["policy_id"] == policy_id), None)
    if proc is None or pol is None:
        return None
    excl = next((e for e in pol["exclusions"] if e["code"] == code), None)
    return {"code": code,
            "description": proc["description"],
            "requires_preauth": proc["requires_preauth"],
            "excluded": excl is not None,
            "exclusion_rule": excl["rule"] if excl else None}


def get_preauthorisation(member_id, procedure_code, date_of_service):
    """Was permission granted BEFORE treatment, and is it still good?

    WHAT IT DOES   looks for an approval matching this member AND this
                   procedure AND valid on this date.
    READS          data_A/preauthorisations.json
    RETURNS        {preauth_id, member_id, procedure_code, valid_from,
                    valid_to} or None
    RETURNS NONE   in TWO different situations that this tool cannot tell
                   apart: no approval was ever granted, OR one exists but
                   had expired before the date of service.
    WATCH OUT      >>> NONE DOES NOT MEAN "NOT COVERED". <<<

    This is the single most expensive misreading available in Problem A.
    None means THE EVIDENCE IS MISSING, which under the routing table is
    a REQUEST - "pre-authorisation reference for 62480, valid on
    2026-09-02" - naming the code and the date. It is not a refusal, and
    deciding otherwise fails the case.

    ALL THREE conditions must hold for a match. An approval for the right
    procedure belonging to another member does not count. An approval for
    the right member and procedure that expired the day before treatment
    does not count either - the shipped data has one of each, precisely
    so a partial match is punished.

    Call this ONLY when check_coverage said requires_preauth is True.
    """
    for pa in _load("A", "preauthorisations"):
        if (pa["member_id"] == member_id
                and pa["procedure_code"] == procedure_code
                and pa["valid_from"] <= date_of_service <= pa["valid_to"]):
            return pa
    return None


def check_duplicate_claim(member_id, hospital_id, date_of_service, lines):
    """Has this episode already been decided?

    WHAT IT DOES   compares the claim against the claims history on ALL
                   FOUR facts.
    READS          data_A/decided_claims.json
    RETURNS        the prior decision row, or None
    RETURNS NONE   when nothing matches - which is the normal case and
                   means carry on.
    WATCH OUT      THE CLAIM ID IS NOT ONE OF THE FACTS. A resubmission
                   arrives with a NEW id, so matching on it finds nothing,
                   ever, and the case fails silently.

    MATCH ON ALL FOUR: member, hospital, date of service, lines. The
    shipped history holds four rows and only ONE queued claim is a true
    duplicate of any of them. The other three history rows are
    NEAR-MISSES, each differing from a real claim on exactly one fact:

        CLM-8710  vs CLM-8933   nothing differs - the true duplicate
        CLM-8702  vs CLM-8850   the date of service differs
        CLM-8726  vs CLM-8960   the LINES differ
        CLM-8688  vs nothing    just history to walk past

    So an agent matching on the date alone, or on member and date, or on
    member and hospital and date, WRONGLY ESCALATES a claim that is
    perfectly fine. Only the full comparison gets all fifteen right. The
    near-misses are in the data deliberately, to make that testable.
    """
    def norm(ls):
        return sorted((l["code"], l["amount"]) for l in ls)
    for d in _load("A", "decided_claims"):
        if (d["member_id"] == member_id
                and d["hospital_id"] == hospital_id
                and d["date_of_service"] == date_of_service
                and norm(d["lines"]) == norm(lines)):
            return d
    return None


def issue_decision_letter(claim_id, decision, lines_resolved, approved_total,
                          refused_total=0):
    """>>> THE IRREVERSIBLE STEP FOR PROBLEM A <<<

    WHAT IT DOES   sends the decision to the member. The insurer is now
                   committed to it.
    READS          nothing - it WRITES, conceptually
    RETURNS        a confirmation carrying the totals for the record
    WATCH OUT      everything before this can be re-run harmlessly. This
                   one cannot be taken back, which is what makes it the
                   gated action - see GATED_ACTION below.

    IT IS A TURN LIKE ANY OTHER. Gated, not free. Appendix A's CLM-8842
    record counts it as turn 4 of 4, and your D2(c) arithmetic has to
    count it too.

    `lines_resolved` is here on purpose: it forces the agent to state how
    many lines it actually disposed of, which makes "I only checked the
    first line" visible in the record instead of invisible.
    """
    return {"sent": True, "claim_id": claim_id, "decision": decision,
            "lines_resolved": lines_resolved,
            "approved_total": approved_total, "refused_total": refused_total}


# =====================================================================
# THE REGISTRY
# =====================================================================
# What the agent is allowed to call, per problem. Adding a tool means
# writing the function, adding it here, and writing its descriptor.
#
# resolve_routing IS DELIBERATELY NOT HERE. It is never something the model
# calls - agent.py invokes it directly once check_referral_criteria and
# lookup_patient have both returned, in EVERY run regardless of
# config.DECISION_MODE. This is not an oversight to "fix" by registering it.
REGISTRY = {
    "B": {
        "get_referral": get_referral,
        "lookup_patient": lookup_patient,
        "check_referral_criteria": check_referral_criteria,
        "get_clinic_slots": get_clinic_slots,
        "book_slot": book_slot,
        "as_of": as_of,
    },
    "A": {
        "get_claim": get_claim,
        "lookup_policy": lookup_policy,
        "lookup_hospital": lookup_hospital,
        "check_coverage": check_coverage,
        "get_preauthorisation": get_preauthorisation,
        "check_duplicate_claim": check_duplicate_claim,
        "issue_decision_letter": issue_decision_letter,
    },
}

# THE ONE IRREVERSIBLE ACTION PER PROBLEM. Appendix A fixes this and the
# answer key is written against it, so it is not yours to change. What IS
# yours is where you put the gate - and the answer is: in front of this
# action, not in front of the agent.
GATED_ACTION = {"B": "book_slot", "A": "issue_decision_letter"}


# =====================================================================
# THE SIX-FIELD DESCRIPTORS  (D2b)
# =====================================================================
# Two worked examples. Write one for EVERY tool you ship, and note that
# the descriptor is what the MODEL reads - the comments above are what
# YOU read. They overlap, but they are not the same document: a
# descriptor is written to be acted on, a comment to be understood.
DESCRIPTORS = {
    # ---- Problem B -------------------------------------------------
    "get_referral": {
        "name": "get_referral",
        "purpose": "Fetch referral details.",
        "when": "Turn 1 only.",
        "args": {"referral_id": "str, case ID"},
        "returns": "{referral_id, patient_id, referring_clinic, specialty, date_received, clinical_summary, tests_attached, tests_attached_on}",
        "failure": "Returns None if ID invalid. Stop run if missing."
    },
    "lookup_patient": {
        "name": "lookup_patient",
        "purpose": "Fetch patient info and existing appointments.",
        "when": "After get_referral (can batch with criteria check).",
        "args": {"patient_id": "str, from referral"},
        "returns": "{patient: {patient_id, date_of_birth, existing_appointments[]}, contact: {method, value}}",
        "failure": "Returns None if patient missing. Empty existing_appointments is normal."
    },
    "check_referral_criteria": {
        "name": "check_referral_criteria",
        "purpose": "Evaluate referral against protocol (red flags, department, missing tests, band).",
        "when": "Immediately after get_referral.",
        "args": {"specialty": "str, referral code", "referral_id": "str, case ID"},
        "returns": "{red_flag_term, right_department, missing_tests, band, window_weeks}",
        "failure": "Returns None if not found. Reports facts only; does not derive decision. Default band is 'routine'."
    },
    "book_slot": {
        "name": "book_slot",
        "purpose": "Commit appointment slot (Irreversible).",
        "when": "Last step only, after all checks pass and valid slot found.",
        "args": {"clinic": "str", "date": "str", "time": "str", "referral_id": "str"},
        "returns": "{booked: true, clinic, date, time, referral_id}",
        "failure": "GATED. May require human approval depending on autonomy setting. Held state is a valid outcome."
    },
    "as_of": {
        "name": "as_of",
        "purpose": "Get reference date for window calculations.",
        "when": "Before window calculation.",
        "args": {},
        "returns": "date string ('YYYY-MM-DD')",
        "failure": "Never fails. Windows count from this date."
    },
    "get_clinic_slots": {
        "name": "get_clinic_slots",
        "purpose": "Find open clinic slots for specialty and band within date window.",
        "when": "AFTER criteria/patient gates pass.",
        "args": {"specialty": "str, e.g. 'OPH'", "band": "str, REQUIRED (urgent|soon|routine)", "from/to": "str dates from as_of()"},
        "returns": "list of {clinic, specialty, band, date, time, capacity_remaining}",
        "failure": "Returns [] if no slot. Escalates to 'no_slot_in_window'. Do NOT expand window or alter band."
    },

    # ---- Problem A -------------------------------------------------
    "get_claim": {
        "name": "get_claim",
        "purpose": "Fetch claim details.",
        "when": "Turn 1 only.",
        "args": {"claim_id": "str, case ID"},
        "returns": "{claim_id, member_id, hospital_id, date_of_service, narrative, documents[], lines[{code, amount}]}",
        "failure": "Returns None if ID invalid. Check every line item."
    },
    "lookup_policy": {
        "name": "lookup_policy",
        "purpose": "Fetch member policy and remaining limit.",
        "when": "After get_claim.",
        "args": {"member_id": "str"},
        "returns": "{member: {...}, policy: {status, start_date, end_date, annual_limit, used_to_date, exclusions[]}, remaining: int}",
        "failure": "Returns None if missing. Use `remaining`, not annual_limit."
    },
    "lookup_hospital": {
        "name": "lookup_hospital",
        "purpose": "Check hospital panel status.",
        "when": "After get_claim.",
        "args": {"hospital_id": "str"},
        "returns": "{hospital_id, name, panel (bool), country}",
        "failure": "Returns None if missing. panel=false changes phrasing, not decision."
    },
    "check_coverage": {
        "name": "check_coverage",
        "purpose": "Check if procedure code is payable under policy.",
        "when": "ONCE PER LINE in same turn.",
        "args": {"code": "str", "policy_id": "str, REQUIRED"},
        "returns": "{code, description, requires_preauth (bool), excluded (bool), exclusion_rule}",
        "failure": "Returns None if invalid. requires_preauth drives preauth check; excluded refuses only that line."
    },
    "check_duplicate_claim": {
        "name": "check_duplicate_claim",
        "purpose": "Check if episode was already decided.",
        "when": "Before decision.",
        "args": {"member_id": "str", "hospital_id": "str", "date_of_service": "str", "lines": "list"},
        "returns": "prior decision row, or None",
        "failure": "Returns None if clean. Match ALL FOUR facts."
    },
    "issue_decision_letter": {
        "name": "issue_decision_letter",
        "purpose": "Send decision to member (Irreversible).",
        "when": "Last step, after all lines decided.",
        "args": {"claim_id": "str", "decision": "str", "lines_resolved": "int", "approved_total": "int", "refused_total": "int"},
        "returns": "{sent: true, claim_id, decision, lines_resolved, approved_total, refused_total}",
        "failure": "GATED. lines_resolved must equal total claim lines."
    },
    "get_preauthorisation": {
        "name": "get_preauthorisation",
        "purpose": "Find pre-authorisation for member/procedure/date.",
        "when": "ONLY when requires_preauth=true.",
        "args": {"member_id": "str", "procedure_code": "str", "date_of_service": "str"},
        "returns": "{preauth_id, member_id, procedure_code, valid_from, valid_to} or None",
        "failure": "None means missing evidence -> REQUEST INFO, NOT UNCOVERED."
    },
#Streamlined DESCRIPTORS in tools.py to reduce Base Prefix size (B) from 1,451 to 1,033 tokens.
}


def call(problem, name, args):
    """Dispatch a tool call by name.

    WATCH OUT      unknown tool names fail LOUDLY (that KeyError is
                   deliberate - a silent no-op here would produce a run
                   that looks fine and decided nothing on evidence it
                   never gathered). A wrong ARGUMENT SHAPE is a different
                   thing: that is untrusted output from a live model, not
                   an internal bug, and a live model can call a real tool
                   with a missing, extra or mistyped argument. Seen live
                   (deepseek/deepseek-chat-v3.1): check_referral_criteria
                   called with 'specialty' omitted, which raised a bare
                   TypeError that took the ENTIRE run down - not just
                   that one case, every case queued after it too. Caught
                   here and turned into an observation the agent (and a
                   human reading the record) can see, the same way a
                   tool's own "not found" result already is.
    """
    table = REGISTRY[problem]
    if name not in table:
        raise KeyError(
            "No tool named %r for Problem %s. Available: %s"
            % (name, problem, ", ".join(sorted(table))))
    try:
        return table[name](**args)
    except TypeError as e:
        return {"error": "bad_arguments",
                "detail": "%s(%s) - %s"
                          % (name, ", ".join("%s=%r" % kv for kv in args.items()), e)}
