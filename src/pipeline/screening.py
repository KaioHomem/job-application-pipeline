"""Hard filters.

A posting is skipped when any filter fires. Every skip carries a code and a
sentence explaining it, because "no" without a reason is not auditable and
cannot be reviewed later.

Filters are deliberately conservative: when the posting does not publish a
fact, the filter does not invent one. An unpublished schedule is flagged for a
human, never silently assumed to fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .models import Job, Profile

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "staff", "principal", "manager"]


@dataclass(frozen=True)
class Reason:
    code: str
    message: str


@dataclass
class Decision:
    job: Job
    reasons: list[Reason] = field(default_factory=list)
    flags: list[Reason] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "skip" if self.reasons else "pass"

    @property
    def needs_human(self) -> bool:
        return self.verdict == "pass" and bool(self.flags)

    def explain(self) -> str:
        head = f"{self.verdict.upper()}  {self.job.company} - {self.job.title}"
        lines = [head]
        for r in self.reasons:
            lines.append(f"  skip [{r.code}] {r.message}")
        for r in self.flags:
            lines.append(f"  flag [{r.code}] {r.message}")
        return "\n".join(lines)


Filter = Callable[[Job, Profile], Reason | None]


def closed(job: Job, profile: Profile) -> Reason | None:
    if job.closed:
        return Reason("closed", "Posting is closed.")
    return None


def affirmative(job: Job, profile: Profile) -> Reason | None:
    # Affirmative-action postings restricted to a group the candidate does not
    # belong to. Eligibility is never guessed here: the caller sets the flag.
    if job.affirmative_only:
        return Reason("affirmative", "Restricted to an affirmative-action group.")
    return None


def location(job: Job, profile: Profile) -> Reason | None:
    model = job.work_model.casefold()
    if model == "remote":
        if not profile.accepts_remote:
            return Reason("location", "Remote, but the profile does not accept remote work.")
        if job.country.casefold() != profile.country.casefold():
            return Reason(
                "location",
                f"Remote from {job.country}; the profile works from {profile.country}.",
            )
        return None
    city = (job.city or "").casefold()
    if city and city in profile.onsite_cities:
        return None
    where = job.city or "an unpublished city"
    return Reason("location", f"{model.capitalize()} in {where}; outside the commutable area.")


def schedule(job: Job, profile: Profile) -> Reason | None:
    if job.schedule is None:
        return None  # handled by flag_unpublished_schedule
    if profile.availability.contains(job.schedule):
        return None
    return Reason(
        "schedule",
        f"Shift {job.schedule} falls outside the availability window "
        f"{profile.availability}.",
    )


def seniority(job: Job, profile: Profile) -> Reason | None:
    level = job.seniority.casefold()
    if level not in SENIORITY_ORDER:
        return None
    if SENIORITY_ORDER.index(level) > SENIORITY_ORDER.index(profile.max_seniority):
        return Reason("seniority", f"Posting is {level}; the profile targets up to {profile.max_seniority}.")
    return None


def degree(job: Job, profile: Profile) -> Reason | None:
    if job.requires_completed_degree and profile.education_status != "graduated":
        return Reason("degree", "A completed degree is mandatory; the candidate is still enrolled.")
    if job.accepted_fields:
        accepted = [f.casefold() for f in job.accepted_fields]
        if profile.education_field.casefold() not in accepted:
            return Reason(
                "field",
                f"Accepted fields are {', '.join(job.accepted_fields)}; "
                f"the candidate studies {profile.education_field}.",
            )
    return None


def tech_evidence(job: Job, profile: Profile) -> Reason | None:
    """A central technology with no evidence in the profile is a hard stop.

    This is the filter that keeps the pipeline honest. Applying to a role built
    on a framework the candidate has never used produces an interview that
    collapses, not an opportunity.
    """
    missing = [t for t in job.required_tech if t.casefold() not in profile.tech_years]
    if missing:
        return Reason("tech", f"Requires {', '.join(missing)}; no evidence in the profile.")
    return None


def experience_years(job: Job, profile: Profile) -> Reason | None:
    short = [
        f"{tech} ({profile.years_in(tech):g} of {needed:g} years)"
        for tech, needed in job.required_years.items()
        if profile.years_in(tech) < needed
    ]
    if short:
        return Reason("experience", f"Below the required experience: {', '.join(short)}.")
    return None


def salary(job: Job, profile: Profile) -> Reason | None:
    if profile.min_monthly_salary is None or job.monthly_salary is None:
        return None
    if job.monthly_salary < profile.min_monthly_salary:
        return Reason(
            "salary",
            f"Pays {job.monthly_salary:.0f}; the floor is {profile.min_monthly_salary:.0f}.",
        )
    return None


FILTERS: list[Filter] = [
    closed,
    affirmative,
    location,
    schedule,
    seniority,
    degree,
    tech_evidence,
    experience_years,
    salary,
]


def flag_unpublished_schedule(job: Job, profile: Profile) -> Reason | None:
    if job.schedule is None:
        return Reason("schedule?", "The posting does not publish a shift; confirm before applying.")
    return None


FLAGS: list[Filter] = [flag_unpublished_schedule]


def screen(job: Job, profile: Profile, filters: list[Filter] | None = None) -> Decision:
    active = FILTERS if filters is None else filters
    reasons = [r for r in (f(job, profile) for f in active) if r is not None]
    flags = [r for r in (f(job, profile) for f in FLAGS) if r is not None]
    return Decision(job=job, reasons=reasons, flags=flags)


def screen_all(jobs: list[Job], profile: Profile) -> list[Decision]:
    return [screen(job, profile) for job in jobs]
