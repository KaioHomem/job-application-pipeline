import pytest

from mcp_server.tools import funnel_summary, screen_posting, simulate_profile, why_skipped


def test_funnel_summary_matches_the_published_record():
    s = funnel_summary()
    assert s["total_postings"] == 189
    assert s["by_status"]["applied"] == 27
    assert sum(s["skipped_by_first_filter"].values()) == s["by_status"]["skipped"]


def test_funnel_summary_states_what_it_cannot_answer():
    s = funnel_summary()
    assert "cannot be re-screened" in s["cannot_answer"]
    assert s["attribution"]["unattributed"] > 0


def test_why_skipped_returns_only_that_bucket():
    out = why_skipped("schedule")
    assert out["count"] == len(out["postings"])
    assert out["count"] > 0
    assert out["meaning"].startswith("the shift collides")


def test_why_skipped_publishes_no_company_name():
    for posting in why_skipped("location")["postings"]:
        assert posting["id"].startswith("Empresa #")
        assert set(posting) == {"id", "role_family", "source", "date", "attribution"}


def test_why_skipped_handles_an_unknown_code():
    out = why_skipped("banana")
    assert out["count"] == 0
    assert out["meaning"] == "unknown code"


def test_simulate_profile_with_no_changes_is_the_baseline():
    out = simulate_profile()
    assert out["passed_before"] == out["passed_after"]
    assert out["gained"] == [] and out["lost"] == []


def test_widening_the_window_frees_postings():
    out = simulate_profile({"availability": {"start": "08:00", "end": "22:00"}})
    assert out["passed_after"] > out["passed_before"]
    assert out["gained"]


def test_narrowing_the_window_costs_postings():
    out = simulate_profile({"availability": {"start": "18:00", "end": "22:00"}})
    assert out["passed_after"] <= out["passed_before"]


def test_simulate_profile_states_its_scope():
    out = simulate_profile()
    assert "cannot be re-screened" in out["scope"]
    assert out["postings"] == 21


def test_screen_posting_runs_the_whole_chain():
    out = screen_posting(
        {
            "title": "Estagio em Dados",
            "work_model": "onsite",
            "city": "Recife",
            "schedule": {"start": "08:00", "end": "17:00"},
            "seniority": "mid",
        }
    )
    assert out["verdict"] == "skip"
    codes = {r["code"] for r in out["reasons"]}
    assert {"location", "schedule", "seniority"} <= codes


def test_screen_posting_flags_an_unpublished_shift_instead_of_passing_it():
    out = screen_posting({"title": "Remote intern", "work_model": "remote", "seniority": "intern"})
    assert out["verdict"] == "pass"
    assert any(f["code"] == "schedule?" for f in out["flags"])


def test_screen_posting_names_a_missing_field():
    assert "work_model" in screen_posting({"title": "No model"})["error"]


def test_screen_posting_honours_a_profile_change():
    posting = {
        "title": "Morning support",
        "work_model": "remote",
        "schedule": {"start": "09:00", "end": "16:00"},
        "seniority": "junior",
    }
    assert screen_posting(posting)["verdict"] == "skip"
    loosened = screen_posting(posting, {"availability": {"start": "08:00", "end": "22:00"}})
    assert loosened["verdict"] == "pass"


def test_a_change_does_not_leak_into_the_next_call():
    simulate_profile({"availability": {"start": "08:00", "end": "22:00"}})
    assert simulate_profile()["gained"] == []
