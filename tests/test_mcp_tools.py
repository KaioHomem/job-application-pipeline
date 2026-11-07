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


# --- screen_posting accepts what a caller plausibly sends -------------------
#
# The hosted server returned a bare "Error executing tool" for a posting whose
# schedule was the string "13:00-22:00". The shape was wrong, but the reply
# taught the caller nothing, which is the worse half of the bug.


def test_a_shift_written_as_a_string_is_screened():
    result = screen_posting(
        {"work_model": "remote", "schedule": "13:00-22:00", "seniority": "junior"}
    )
    assert "error" not in result, result
    assert result["verdict"] in {"pass", "skip"}
    assert not [r for r in result["reasons"] if r["code"] == "schedule"]


def test_the_three_shift_shapes_agree():
    shapes = [
        "08:00-12:00",
        ["08:00", "12:00"],
        {"start": "08:00", "end": "12:00"},
    ]
    verdicts = {
        screen_posting({"work_model": "remote", "schedule": s})["verdict"]
        for s in shapes
    }
    assert len(verdicts) == 1, verdicts


def test_a_morning_shift_still_collides():
    result = screen_posting({"work_model": "remote", "schedule": "08:00-17:00"})
    assert result["verdict"] == "skip"
    assert "schedule" in {r["code"] for r in result["reasons"]}


def test_an_unreadable_shift_explains_itself_instead_of_crashing():
    result = screen_posting({"work_model": "remote", "schedule": "sometime"})
    assert "error" in result
    assert "sometime" in result["error"]
    assert "13:00-22:00" in result["hint"]


def test_required_years_as_a_bare_number_is_refused_not_guessed():
    result = screen_posting(
        {"work_model": "remote", "required_tech": ["python"], "required_years": 3}
    )
    assert "error" in result
    assert "per technology" in result["error"]


def test_required_years_per_technology_is_screened():
    result = screen_posting(
        {"work_model": "remote", "required_tech": ["python"], "required_years": {"python": 9}}
    )
    assert "error" not in result, result
    assert "experience" in {r["code"] for r in result["reasons"]}


def test_an_omitted_shift_raises_a_flag_rather_than_passing_silently():
    result = screen_posting({"work_model": "remote"})
    assert "error" not in result, result
    assert "schedule?" in {f["code"] for f in result["flags"]}
