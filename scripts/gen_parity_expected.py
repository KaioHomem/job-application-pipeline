#!/usr/bin/env python3
"""Generate the decision oracle both implementations are pinned to.

`tests/fixtures/parity_expected.json` is the committed output of the Python
filters over `tests/fixtures/parity_corpus.json`. The Python test regenerates
it and compares, so Python drift fails CI; the JavaScript test reads the same
file, so port drift fails CI too.

    python scripts/gen_parity_expected.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from pipeline.models import Job, Profile, TimeWindow  # noqa: E402
from pipeline.screening import screen  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "tests", "fixtures", "parity_corpus.json")
EXPECTED = os.path.join(ROOT, "tests", "fixtures", "parity_expected.json")


def _profile(raw: dict) -> Profile:
    window = raw["availability"]
    return Profile(
        name=raw["name"],
        city=raw["city"],
        state=raw["state"],
        country=raw["country"],
        accepts_remote=raw["accepts_remote"],
        onsite_cities=[c.casefold() for c in raw.get("onsite_cities", [])],
        availability=TimeWindow.parse(window["start"], window["end"]),
        education_status=raw["education"]["status"],
        education_field=raw["education"]["field"],
        expected_graduation=raw["education"].get("expected_graduation"),
        max_seniority=raw.get("max_seniority", "junior"),
        min_monthly_salary=raw.get("min_monthly_salary"),
        tech_years={k.casefold(): v for k, v in raw.get("tech_years", {}).items()},
    )


def build_expected(corpus: dict) -> list[dict]:
    """Screen every job under every profile and return the sorted decisions.

    Messages are part of the contract, not just codes: the page prints them,
    so a port that produces the right verdict with different wording has still
    drifted from the engine it claims to be.
    """
    rows: list[dict] = []
    for name, raw_profile in corpus["profiles"].items():
        profile = _profile(raw_profile)
        for raw_job in corpus["jobs"]:
            job = Job.from_dict(raw_job)
            decision = screen(job, profile)
            rows.append(
                {
                    "profile": name,
                    "url": job.url,
                    "verdict": decision.verdict,
                    "codes": [r.code for r in decision.reasons],
                    "messages": [r.message for r in decision.reasons],
                    "flags": [f.code for f in decision.flags],
                }
            )
    rows.sort(key=lambda r: (r["profile"], r["url"]))
    return rows


def main() -> int:
    with open(CORPUS, encoding="utf-8") as fh:
        corpus = json.load(fh)
    rows = build_expected(corpus)
    with open(EXPECTED, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(rows)} decisions to {os.path.relpath(EXPECTED, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
