"""Funnel report.

Counts what the tracker actually holds. Skip reasons are grouped by the code
the screening filters emitted, not by a keyword guess over free text, so the
report says which rule did the work.
"""

from __future__ import annotations

import re
from collections import Counter

from .tracker import Tracker

CODE = re.compile(r"\[([a-z?]+)\]")


def funnel(tracker: Tracker) -> dict[str, int]:
    return dict(Counter(row.status for row in tracker.rows))


def skip_reasons(tracker: Tracker) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in tracker.rows:
        if row.status != "skipped":
            continue
        codes = CODE.findall(row.notes)
        counter.update(codes or ["unclassified"])
    return dict(counter.most_common())


def sources(tracker: Tracker, status: str | None = None) -> dict[str, int]:
    rows = tracker.rows if status is None else [r for r in tracker.rows if r.status == status]
    return dict(Counter(r.source for r in rows).most_common())


def proof_coverage(tracker: Tracker) -> tuple[int, int]:
    """(rows with proof, rows claiming applied). These must be equal."""
    applied = [r for r in tracker.rows if r.status == "applied"]
    return sum(1 for r in applied if r.proof), len(applied)


def render(tracker: Tracker) -> str:
    counts = funnel(tracker)
    total = sum(counts.values())
    with_proof, applied = proof_coverage(tracker)
    lines = [f"Postings triaged: {total}", ""]

    lines.append("Funnel")
    for status, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        share = f"{count / total:.0%}" if total else "0%"
        lines.append(f"  {status:<12} {count:>4}  {share:>4}")

    reasons = skip_reasons(tracker)
    if reasons:
        lines += ["", "Why postings were skipped"]
        skipped = sum(reasons.values())
        for code, count in reasons.items():
            lines.append(f"  {code:<12} {count:>4}  {count / skipped:.0%}")

    lines += ["", f"Proof coverage: {with_proof}/{applied} applications have an archived artifact"]
    if applied and with_proof != applied:
        lines.append("  WARNING: an application without proof is not an application")
    return "\n".join(lines)
