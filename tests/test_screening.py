import pytest

from pipeline.models import Job, Profile, TimeWindow
from pipeline.screening import screen

JOBS = "examples/jobs.json"
PROFILE = "config/profile.example.json"


@pytest.fixture(scope="module")
def profile():
    return Profile.load(PROFILE)


@pytest.fixture(scope="module")
def jobs():
    return {job.company: job for job in Job.load_many(JOBS)}


def codes(decision):
    return {r.code for r in decision.reasons}


def test_remote_role_inside_the_window_passes(profile, jobs):
    decision = screen(jobs["Northwind Labs"], profile)
    assert decision.verdict == "pass"
    assert decision.reasons == []


def test_onsite_in_a_commutable_city_passes(profile, jobs):
    assert screen(jobs["Adventure Works"], profile).verdict == "pass"


def test_morning_shift_is_rejected(profile, jobs):
    assert "schedule" in codes(screen(jobs["Contoso Delivery"], profile))


def test_central_tech_without_evidence_is_rejected(profile, jobs):
    decision = screen(jobs["Fabrikam Systems"], profile)
    assert "tech" in codes(decision)
    assert "react" in decision.reasons[0].message


def test_onsite_outside_the_area_is_rejected(profile, jobs):
    assert "location" in codes(screen(jobs["Tailspin Logistica"], profile))


def test_remote_from_another_country_is_rejected(profile, jobs):
    assert "location" in codes(screen(jobs["Globex Remote"], profile))


def test_seniority_above_target_is_rejected(profile, jobs):
    assert "seniority" in codes(screen(jobs["Proseware"], profile))


def test_completed_degree_requirement_is_rejected(profile, jobs):
    assert "degree" in codes(screen(jobs["Litware"], profile))


def test_unrelated_field_is_rejected(profile, jobs):
    assert "field" in codes(screen(jobs["Wide World Importers"], profile))


def test_salary_below_the_floor_is_rejected(profile, jobs):
    assert "salary" in codes(screen(jobs["Trey Research"], profile))


def test_unpublished_schedule_passes_but_is_flagged(profile, jobs):
    decision = screen(jobs["Fabrikam Systems"], profile)
    assert any(f.code == "schedule?" for f in decision.flags)


def test_every_rejection_carries_a_sentence(profile, jobs):
    for job in jobs.values():
        for reason in screen(job, profile).reasons:
            assert reason.message.strip().endswith("."), reason


def test_window_containment():
    window = TimeWindow.parse("12:00", "22:00")
    assert window.contains(TimeWindow.parse("13:00", "19:00"))
    assert not window.contains(TimeWindow.parse("09:00", "16:00"))
    assert not window.contains(TimeWindow.parse("18:00", "23:00"))
    assert str(window) == "12:00-22:00"
