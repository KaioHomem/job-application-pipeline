import pytest

from pipeline.models import Job
from pipeline.report import funnel, proof_coverage, skip_reasons
from pipeline.screening import screen
from pipeline.tracker import DuplicateApplication, ProofRequired, Row, Tracker

SAMPLE = "examples/tracker.sample.csv"


def row(**kw):
    base = dict(
        date="2026-09-20",
        company="Northwind Labs",
        role="Estagio",
        source="example",
        url="https://example.com/jobs/x",
        status="applied",
    )
    base.update(kw)
    return Row(**base)


def test_applied_without_proof_is_refused(tmp_path):
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    with pytest.raises(ProofRequired):
        tracker.add(row())


def test_applied_with_a_missing_proof_file_is_refused(tmp_path):
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    with pytest.raises(ProofRequired):
        tracker.add(row(proof="proofs/nope/confirmation.txt"))


def test_applied_with_proof_is_accepted(tmp_path):
    proof = tmp_path / "proofs" / "x"
    proof.mkdir(parents=True)
    (proof / "confirmation.txt").write_text("ok", encoding="utf-8")
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    tracker.add(row(proof="proofs/x/confirmation.txt"))
    assert len(tracker.rows) == 1


def test_skipped_rows_need_no_proof(tmp_path):
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    tracker.add(row(status="skipped"))
    assert tracker.rows[0].status == "skipped"


def test_the_same_posting_is_not_submitted_twice(tmp_path):
    proof = tmp_path / "proofs" / "x"
    proof.mkdir(parents=True)
    (proof / "confirmation.txt").write_text("ok", encoding="utf-8")
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    tracker.add(row(proof="proofs/x/confirmation.txt"))
    with pytest.raises(DuplicateApplication):
        tracker.add(row(proof="proofs/x/confirmation.txt"))


def test_unknown_status_is_refused():
    with pytest.raises(ValueError):
        row(status="maybe")


def test_round_trip_through_disk(tmp_path):
    path = str(tmp_path / "t.csv")
    tracker = Tracker(path=path, proof_root=str(tmp_path))
    tracker.add(row(status="skipped", notes="[schedule] Morning shift."))
    tracker.save()
    assert Tracker.load(path).rows[0].notes == "[schedule] Morning shift."


def test_a_screening_decision_becomes_a_reviewable_row(tmp_path):
    jobs = {j.company: j for j in Job.load_many("examples/jobs.json")}
    from pipeline.models import Profile

    decision = screen(jobs["Contoso Delivery"], Profile.load("config/profile.example.json"))
    tracker = Tracker(path=str(tmp_path / "t.csv"), proof_root=str(tmp_path))
    saved = tracker.record_skip(decision.job, decision.reasons, today="2026-09-20")
    assert saved.status == "skipped"
    assert "[schedule]" in saved.notes


def test_sample_report_numbers():
    tracker = Tracker.load(SAMPLE)
    counts = funnel(tracker)
    assert counts["applied"] == 5
    assert counts["skipped"] == 13
    with_proof, applied = proof_coverage(tracker)
    assert with_proof == applied == 5
    assert skip_reasons(tracker)["schedule"] == 2
