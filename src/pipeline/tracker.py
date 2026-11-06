"""The tracker, and the rule that makes it trustworthy.

One CSV, one row per posting. A row may only reach status ``applied`` when a
proof file exists on disk, so the funnel cannot drift away from reality: if the
confirmation screen was never captured, the application did not happen.
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import date

STATUSES = ("applied", "skipped", "needs_human", "rejected", "interview", "offer")

FIELDNAMES = ["date", "company", "role", "source", "url", "status", "next_action", "proof", "notes"]


class ProofRequired(RuntimeError):
    """Raised when a row claims ``applied`` without a proof artifact."""


class DuplicateApplication(RuntimeError):
    """Raised when the same posting URL is submitted twice."""


@dataclass
class Row:
    date: str
    company: str
    role: str
    source: str
    url: str
    status: str
    next_action: str = ""
    proof: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}; expected one of {STATUSES}")


@dataclass
class Tracker:
    path: str
    proof_root: str = "."
    rows: list[Row] = field(default_factory=list)

    @classmethod
    def load(cls, path: str, proof_root: str = ".") -> "Tracker":
        tracker = cls(path=path, proof_root=proof_root)
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as fh:
                known = {f.name for f in fields(Row)}
                tracker.rows = [Row(**{k: v for k, v in raw.items() if k in known}) for raw in csv.DictReader(fh)]
        return tracker

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in self.rows:
                writer.writerow(asdict(row))

    def seen(self, url: str) -> Row | None:
        for row in self.rows:
            if row.url == url:
                return row
        return None

    def add(self, row: Row) -> Row:
        existing = self.seen(row.url)
        if existing and existing.status == "applied":
            raise DuplicateApplication(f"{row.url} was already submitted on {existing.date}")
        if row.status == "applied":
            self._require_proof(row)
        if existing:
            self.rows[self.rows.index(existing)] = row
        else:
            self.rows.append(row)
        return row

    def _require_proof(self, row: Row) -> None:
        if not row.proof:
            raise ProofRequired(f"{row.company} - {row.role}: status 'applied' needs a proof file")
        full = os.path.join(self.proof_root, row.proof)
        if not os.path.exists(full):
            raise ProofRequired(f"proof file not found: {full}")

    def record_skip(self, job, reasons, today: str | None = None) -> Row:
        """Persist a screening decision so a rejection is reviewable later."""
        return self.add(
            Row(
                date=today or date.today().isoformat(),
                company=job.company,
                role=job.title,
                source=job.source,
                url=job.url,
                status="skipped",
                notes=" ".join(f"[{r.code}] {r.message}" for r in reasons),
            )
        )
