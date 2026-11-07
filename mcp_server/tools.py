"""The four answers the MCP server can give, as plain functions.

The transport lives in `server.py`; everything that decides an answer lives
here, with no dependency beyond the standard library and `src/pipeline`. That
split is deliberate: these functions are unit-tested without starting a server,
and the `mcp` SDK stays confined to one file.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

from pipeline.models import Job, Profile, TimeWindow
from pipeline.screening import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORD = os.path.join(ROOT, "web", "data", "record.json")
DETAILED = os.path.join(ROOT, "web", "data", "detailed.json")
BASELINE = os.path.join(ROOT, "config", "baseline_profile.json")

BUCKET_PROSE = {
    "location": "the work is somewhere that cannot be reached",
    "schedule": "the shift collides with the availability window",
    "tech": "a central technology has no evidence in the profile",
    "experience": "it asks for more professional years than exist",
    "field": "the field of study is not accepted",
    "affirmative": "it is reserved for a group the candidate is not in",
    "closed": "the posting was already closed",
    "degree": "it requires a degree that is not finished",
    "salary": "it pays below the floor",
    "unattributed": "the reason was kept only as prose and cannot be attributed",
}


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _as_job(raw: dict) -> Job:
    return Job.from_dict(
        {**raw, "company": raw.get("id", "Empresa"), "url": raw.get("url", f"urn:posting:{raw.get('id')}")}
    )


def _baseline() -> Profile:
    return Profile.load(BASELINE)


def _with_changes(profile: Profile, changes: dict) -> Profile:
    """Apply an edit to the baseline profile without mutating it."""
    fields = dict(profile.__dict__)
    if "availability" in changes:
        window = changes["availability"]
        fields["availability"] = TimeWindow.parse(window["start"], window["end"])
    if "min_monthly_salary" in changes:
        fields["min_monthly_salary"] = changes["min_monthly_salary"]
    if "max_seniority" in changes:
        fields["max_seniority"] = changes["max_seniority"]
    if "accepts_remote" in changes:
        fields["accepts_remote"] = changes["accepts_remote"]
    if "onsite_cities" in changes:
        fields["onsite_cities"] = [c.casefold() for c in changes["onsite_cities"]]
    if "tech_years" in changes:
        fields["tech_years"] = {k.casefold(): v for k, v in changes["tech_years"].items()}
    return Profile(**fields)


# --------------------------------------------------------------------- tools


def funnel_summary() -> dict:
    """Counts over the 189-posting record, and what the record cannot answer."""
    record = _load(RECORD)
    status = Counter(r["status"] for r in record)
    skipped = [r for r in record if r["status"] == "skipped"]
    buckets = Counter(r["primary_code"] or "unattributed" for r in skipped)
    classified = sum(1 for r in skipped if r["code_source"])

    return {
        "window": "2026-09-08 to 2026-09-24, seven active days",
        "total_postings": len(record),
        "by_status": dict(status),
        "skipped_by_first_filter": dict(buckets.most_common()),
        "attribution": {
            "classified": classified,
            "unattributed": len(skipped) - classified,
            "caveat": (
                "Most rows predate the bracketed reason codes, so their bucket is derived from "
                "Portuguese prose by keyword rules and marked code_source=classified. Rows that "
                "resisted classification are published unattributed rather than forced into a bucket."
            ),
        },
        "cannot_answer": (
            "The record stores no work model, shift, required technology or seniority, so these "
            "189 postings cannot be re-screened. Use simulate_profile, which runs over the "
            "hand-labelled detailed set instead."
        ),
    }


def why_skipped(code: str) -> dict:
    """The postings a given filter stopped first, anonymised."""
    record = _load(RECORD)
    wanted = code.strip().casefold()
    matches = [
        {
            "id": r["id"],
            "role_family": r["role_family"],
            "source": r["source"],
            "date": r["date"],
            "attribution": r["code_source"] or "unattributed",
        }
        for r in record
        if r["status"] == "skipped" and (r["primary_code"] or "unattributed") == wanted
    ]
    return {
        "code": wanted,
        "meaning": BUCKET_PROSE.get(wanted, "unknown code"),
        "count": len(matches),
        "postings": matches,
        "note": "Company names are not published. Each posting is an opaque id.",
    }


def simulate_profile(changes: dict | None = None) -> dict:
    """Re-screen the detailed set under an edited profile, and name the trade."""
    jobs = [_as_job(raw) for raw in _load(DETAILED)]
    base = _baseline()
    edited = _with_changes(base, changes or {})

    def run(profile: Profile) -> dict:
        decisions = {j.url: screen(j, profile) for j in jobs}
        return {
            "passed": sum(1 for d in decisions.values() if d.verdict == "pass"),
            "decisions": decisions,
        }

    before, after = run(base), run(edited)
    gained = [u for u, d in after["decisions"].items() if d.verdict == "pass" and before["decisions"][u].verdict == "skip"]
    lost = [u for u, d in after["decisions"].items() if d.verdict == "skip" and before["decisions"][u].verdict == "pass"]

    def title(url: str) -> str:
        return after["decisions"][url].job.title

    return {
        "postings": len(jobs),
        "passed_before": before["passed"],
        "passed_after": after["passed"],
        "gained": [title(u) for u in gained],
        "lost": [title(u) for u in lost],
        "by_first_filter": dict(
            Counter(
                d.reasons[0].code for d in after["decisions"].values() if d.verdict == "skip"
            ).most_common()
        ),
        "scope": (
            f"These {len(jobs)} postings are the ones whose every field could be recovered. The "
            "other 168 in the record cannot be re-screened and are not counted here."
        ),
    }


def _normalize_schedule(raw: Any) -> dict[str, str] | None:
    """Accept the three shapes a caller plausibly sends for a shift.

    `Job.from_dict` wants {"start": "13:00", "end": "22:00"}. A model reading a
    tool description writes "13:00-22:00" at least as often, and a list is the
    next guess. All three mean the same shift, so all three are accepted here
    rather than in the pipeline, which keeps one canonical shape on disk.
    """
    if raw in (None, "", {}, []):
        return None
    if isinstance(raw, dict):
        if "start" in raw and "end" in raw:
            return {"start": str(raw["start"]), "end": str(raw["end"])}
        raise ValueError('schedule object needs both "start" and "end", as in {"start": "13:00", "end": "22:00"}')
    if isinstance(raw, (list, tuple)):
        if len(raw) == 2:
            return {"start": str(raw[0]), "end": str(raw[1])}
        raise ValueError('schedule list needs exactly two times, as in ["13:00", "22:00"]')
    if isinstance(raw, str):
        # Dashes split anywhere; word separators only between spaces, so "Noturno"
        # is not torn apart at its own "to".
        parts = [p.strip() for p in re.split(r"\s*[-–—]\s*|\s+(?:to|às|as|até)\s+", raw) if p.strip()]
        if len(parts) == 2:
            return {"start": parts[0], "end": parts[1]}
        raise ValueError(f'cannot read {raw!r} as a shift; write it as "13:00-22:00"')
    raise ValueError(f"schedule has type {type(raw).__name__}; expected a string, a list or an object")


def _normalize_required_years(raw: Any) -> dict[str, float]:
    """`required_years` is per technology, not one number for the whole role.

    A bare number is the obvious thing to send and the wrong thing to guess at:
    two years of Python and two years of anything are different postings. So
    this refuses instead of spreading the number over the tech list.
    """
    if raw in (None, "", {}):
        return {}
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    if isinstance(raw, (int, float)):
        raise ValueError(
            f"required_years is per technology, not a single total; write "
            f'{{"python": {float(raw):g}}} rather than {raw!r}'
        )
    raise ValueError(f"required_years has type {type(raw).__name__}; expected an object keyed by technology")


def screen_posting(posting: dict, changes: dict | None = None) -> dict:
    """Run the nine filters over a posting the caller describes."""
    if not isinstance(posting, dict):
        return {"error": f"posting must be an object, not {type(posting).__name__}"}
    required = {"work_model"}
    missing = sorted(required - set(posting))
    if missing:
        return {"error": f"missing required field(s): {', '.join(missing)}"}

    raw = {
        "company": posting.get("company", "unnamed"),
        "title": posting.get("title", "unnamed posting"),
        "url": posting.get("url", "urn:posting:ad-hoc"),
        **posting,
    }
    try:
        raw["schedule"] = _normalize_schedule(raw.get("schedule"))
        raw["required_years"] = _normalize_required_years(raw.get("required_years"))
        job = Job.from_dict(raw)
        decision = screen(job, _with_changes(_baseline(), changes or {}))
    except (ValueError, TypeError, KeyError) as exc:
        # An opaque "Error executing tool" teaches a caller nothing. Say what
        # was wrong with the input so the next call can be right.
        return {
            "error": str(exc) or f"{type(exc).__name__} while reading the posting",
            "hint": (
                'work_model is required and must be "remote", "hybrid" or "onsite". '
                'schedule is a shift such as "13:00-22:00". required_years is an object '
                'keyed by technology, such as {"python": 1}.'
            ),
        }
    return {
        "verdict": decision.verdict,
        "reasons": [{"code": r.code, "message": r.message} for r in decision.reasons],
        "flags": [{"code": f.code, "message": f.message} for f in decision.flags],
        "note": (
            "Every filter is evaluated; the chain does not stop at the first failure. "
            "A schedule? flag means the posting published no shift and that was not resolved "
            "in the candidate's favour."
        ),
    }
