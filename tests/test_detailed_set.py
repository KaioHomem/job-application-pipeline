import csv
import json
import os
import re

from pipeline.models import Job, Profile
from pipeline.screening import screen

DETAILED = os.path.join("web", "data", "detailed.json")
RECORD = os.path.join("web", "data", "record.json")
BASELINE = os.path.join("config", "baseline_profile.json")

EVIDENCE = {"posting still live", "archived note", "proof artifact"}
OUTCOMES = {"applied", "skipped", "needs_human", "rejected"}


def detailed():
    with open(DETAILED, encoding="utf-8") as fh:
        return json.load(fh)


def test_every_detailed_posting_loads_as_a_job():
    for raw in detailed():
        job = Job.from_dict({**raw, "company": raw["id"], "url": f"https://example.invalid/{raw['id']}"})
        assert job.work_model in {"remote", "hybrid", "onsite"}


def test_every_id_is_anonymous_and_known_to_the_record():
    with open(RECORD, encoding="utf-8") as fh:
        known = {r["id"] for r in json.load(fh)}
    for raw in detailed():
        assert re.fullmatch(r"Empresa #\d{3}", raw["id"]), raw["id"]
        assert raw["id"] in known, f"{raw['id']} is not in the published record"


def test_no_company_name_survives_into_the_detailed_set():
    tracker = os.environ.get("PRIVATE_TRACKER")
    if not tracker or not os.path.exists(tracker):
        return  # the private tracker is not available in CI, which is the point
    with open(DETAILED, encoding="utf-8") as fh:
        text = fh.read().casefold()
    with open(tracker, newline="", encoding="utf-8") as fh:
        names = {(row["Company"] or "").strip() for row in csv.DictReader(fh)}
    for name in names:
        if len(name) > 3:
            assert name.casefold() not in text, f"company name leaked: {name}"


def test_every_posting_declares_its_evidence():
    for raw in detailed():
        assert raw["recovered_from"] in EVIDENCE, raw


def test_every_posting_declares_its_real_outcome():
    for raw in detailed():
        assert raw["outcome"] in OUTCOMES, raw


def test_the_baseline_profile_carries_no_contact_details():
    with open(BASELINE, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert not {"email", "phone", "address", "cpf", "cep"} & raw.keys()
    Profile.load(BASELINE)


def test_the_detailed_set_produces_both_verdicts():
    profile = Profile.load(BASELINE)
    verdicts = set()
    for raw in detailed():
        job = Job.from_dict({**raw, "company": raw["id"], "url": f"https://example.invalid/{raw['id']}"})
        verdicts.add(screen(job, profile).verdict)
    assert verdicts == {"pass", "skip"}


def test_the_engine_agrees_with_the_recorded_outcome():
    """A posting marked skipped must actually be rejected by the filters.

    A posting that was applied to, or that stopped for a human, must pass them.
    If this fails, either the labelling is wrong or the filters changed.
    """
    profile = Profile.load(BASELINE)
    for raw in detailed():
        job = Job.from_dict({**raw, "company": raw["id"], "url": f"https://example.invalid/{raw['id']}"})
        decision = screen(job, profile)
        expected = "skip" if raw["outcome"] == "skipped" else "pass"
        assert decision.verdict == expected, (
            f"{raw['id']} {raw['title']}: outcome={raw['outcome']} "
            f"but the engine says {decision.verdict} "
            f"({[r.code for r in decision.reasons]})"
        )


def test_widening_the_window_changes_the_outcome_for_someone():
    """The counterfactual the page is built around has to actually move."""
    profile = Profile.load(BASELINE)
    jobs = [
        Job.from_dict({**raw, "company": raw["id"], "url": f"https://example.invalid/{raw['id']}"})
        for raw in detailed()
    ]
    before = sum(1 for j in jobs if screen(j, profile).verdict == "pass")

    from pipeline.models import TimeWindow

    morning = Profile(**{**profile.__dict__, "availability": TimeWindow.parse("08:00", "22:00")})
    after = sum(1 for j in jobs if screen(j, morning).verdict == "pass")
    assert after > before, "widening the availability window freed no posting"
