"""Data models shared by the pipeline.

Everything is a plain dataclass loaded from JSON so the pipeline can run with
the standard library only. No network, no database, no vendor SDK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _hhmm(value: str) -> int:
    """'12:00' -> 720. Minutes since midnight, so windows are plain integers."""
    hours, _, minutes = value.partition(":")
    return int(hours) * 60 + int(minutes or 0)


@dataclass(frozen=True)
class TimeWindow:
    start: int
    end: int

    @classmethod
    def parse(cls, start: str, end: str) -> "TimeWindow":
        return cls(_hhmm(start), _hhmm(end))

    def contains(self, other: "TimeWindow") -> bool:
        return self.start <= other.start and other.end <= self.end

    def __str__(self) -> str:
        def fmt(m: int) -> str:
            return f"{m // 60:02d}:{m % 60:02d}"

        return f"{fmt(self.start)}-{fmt(self.end)}"


@dataclass
class Profile:
    """The candidate. The single source of truth for every filter."""

    name: str
    city: str
    state: str
    country: str
    accepts_remote: bool
    onsite_cities: list[str]
    availability: TimeWindow
    education_status: str  # "enrolled" | "graduated"
    education_field: str
    expected_graduation: int | None
    max_seniority: str  # highest seniority the candidate will apply to
    min_monthly_salary: float | None
    # Tech the candidate can honestly claim, with professional years.
    # Study-only practice is years == 0 and must never be reported as experience.
    tech_years: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "Profile":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        window = raw["availability"]
        return cls(
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

    def years_in(self, tech: str) -> float:
        return self.tech_years.get(tech.casefold(), 0.0)


@dataclass
class Job:
    """One posting, already parsed into fields. Parsing HTML is out of scope."""

    company: str
    title: str
    url: str
    source: str
    work_model: str  # "remote" | "hybrid" | "onsite"
    city: str | None = None
    state: str | None = None
    country: str = "Brasil"
    schedule: TimeWindow | None = None  # None = not published
    seniority: str = "junior"
    required_tech: list[str] = field(default_factory=list)
    required_years: dict[str, float] = field(default_factory=dict)
    requires_completed_degree: bool = False
    accepted_fields: list[str] = field(default_factory=list)
    monthly_salary: float | None = None
    affirmative_only: bool = False
    closed: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Job":
        schedule = None
        if raw.get("schedule"):
            schedule = TimeWindow.parse(raw["schedule"]["start"], raw["schedule"]["end"])
        return cls(
            company=raw["company"],
            title=raw["title"],
            url=raw["url"],
            source=raw.get("source", "unknown"),
            work_model=raw["work_model"],
            city=raw.get("city"),
            state=raw.get("state"),
            country=raw.get("country", "Brasil"),
            schedule=schedule,
            seniority=raw.get("seniority", "junior"),
            required_tech=raw.get("required_tech", []),
            required_years=raw.get("required_years", {}),
            requires_completed_degree=raw.get("requires_completed_degree", False),
            accepted_fields=raw.get("accepted_fields", []),
            monthly_salary=raw.get("monthly_salary"),
            affirmative_only=raw.get("affirmative_only", False),
            closed=raw.get("closed", False),
        )

    @classmethod
    def load_many(cls, path: str) -> list["Job"]:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return [cls.from_dict(item) for item in raw]
