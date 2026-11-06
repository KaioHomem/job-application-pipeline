"""The gate that rejects a tailored CV.

Two gates run over the plain text extracted from a generated CV:

TRUTH  - every line must trace back to the master CV, and nothing may claim
         seniority, metrics, tooling or credentials the candidate does not have.
ATS    - the file must survive an applicant tracking system parser.

The gate never edits the CV. It only fails it. A validator that silently
rewrites its input teaches you nothing about the generator that produced it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Fold a line so that comparisons ignore accents, case and list markers."""
    text = strip_accents(text).lower()
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    text = re.sub(r"^[\s>*\-]+", "", text)
    text = re.sub(r"[`*_]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


@dataclass
class Rules:
    section_headers: list[str]
    confirmed_skills: list[str]
    blocked_patterns: list[tuple[str, str]]
    skill_line_prefixes: list[str]
    in_progress_markers: list[str]
    max_words: int = 500
    max_line_length: int = 120
    min_sections: int = 6
    min_bullets: int = 4

    @classmethod
    def load(cls, path: str) -> "Rules":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls(
            section_headers=[h.upper() for h in raw["section_headers"]],
            confirmed_skills=[normalize(s) for s in raw["confirmed_skills"]],
            blocked_patterns=[(b["pattern"], b["message"]) for b in raw["blocked_patterns"]],
            skill_line_prefixes=raw.get("skill_line_prefixes", []),
            in_progress_markers=raw.get("in_progress_markers", []),
            max_words=raw.get("max_words", 500),
            max_line_length=raw.get("max_line_length", 120),
            min_sections=raw.get("min_sections", 6),
            min_bullets=raw.get("min_bullets", 4),
        )


@dataclass
class Check:
    gate: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)

    def add(self, gate: str, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(gate, name, passed, detail))

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def approved(self) -> bool:
        return not self.failed

    def render(self) -> str:
        width = max(len(c.name) for c in self.checks)
        lines: list[str] = []
        current = None
        for check in self.checks:
            if check.gate != current:
                lines.append("")
                lines.append(check.gate)
                lines.append("-" * len(check.gate))
                current = check.gate
            mark = "PASS" if check.passed else "FAIL"
            lines.append(f"  [{mark}] {check.name:<{width}} {check.detail}")
        passed = len(self.checks) - len(self.failed)
        lines.append("")
        lines.append(
            f"RESULT: {'APPROVED' if self.approved else 'REJECTED'} "
            f"({passed}/{len(self.checks)} checks passed)"
        )
        return "\n".join(lines)


GRAPHIC_CHARS = re.compile(r"[•●▪→✓✔]|[\U0001F300-\U0001FAFF]")
DATE_FORMAT = re.compile(r"20\d\d\s*-\s*(20\d\d|presente|present)", re.IGNORECASE)


def _source_fragments(master_text: str) -> set[str]:
    """Every line and sentence of the master, normalized, for containment."""
    out: set[str] = set()
    for raw in master_text.splitlines():
        line = normalize(raw)
        if not line:
            continue
        out.add(line)
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip(" .")
            if len(part) > 12:
                out.add(part)
    return out


def _contained(line: str, fragments: set[str]) -> bool:
    needle = normalize(line)
    if not needle:
        return True
    if needle in fragments:
        return True
    return any(needle in frag for frag in fragments if len(frag) >= len(needle))


def validate(cv_text: str, master_text: str, rules: Rules) -> Result:
    lines = [line.rstrip() for line in cv_text.splitlines()]
    content = [line for line in lines if line.strip()]
    flat = normalize(cv_text)
    fragments = _source_fragments(master_text)
    result = Result()

    truth = "TRUTH GATE"
    result.add(truth, "1. text extraction", len(content) >= 15, f"{len(content)} content lines")

    headers = set(rules.section_headers)
    orphans = [
        line.strip()
        for line in content
        if strip_accents(line.strip()).upper() not in headers and not _contained(line, fragments)
    ]
    result.add(
        truth,
        "2. contained in master",
        not orphans,
        "OK" if not orphans else f"{len(orphans)} orphan line(s): {orphans[:2]}",
    )

    hits = [msg for pattern, msg in rules.blocked_patterns if re.search(pattern, flat)]
    result.add(
        truth,
        "3. no unsupported claims",
        not hits,
        "OK" if not hits else "; ".join(sorted(set(hits))),
    )

    in_progress = any(re.search(marker, flat) for marker in rules.in_progress_markers)
    result.add(
        truth,
        "4. degree marked in progress",
        in_progress or not rules.in_progress_markers,
        "marker present" if in_progress else "missing",
    )

    unknown: list[str] = []
    prefix = re.compile(r"^(" + "|".join(rules.skill_line_prefixes) + r"):") if rules.skill_line_prefixes else None
    if prefix:
        for line in content:
            folded = normalize(line)
            if not prefix.match(folded):
                continue
            for item in re.split(r",| e |\band\b", folded.split(":", 1)[1]):
                item = item.strip(" .")
                if len(item) < 2:
                    continue
                if not any(item in skill or skill in item for skill in rules.confirmed_skills):
                    unknown.append(item)
    result.add(
        truth,
        "5. only confirmed skills",
        not unknown,
        "OK" if not unknown else f"outside the confirmed list: {unknown}",
    )

    ats = "ATS GATE"
    result.add(ats, "A. no layout tables", "|---" not in cv_text and "+--" not in cv_text, "OK")
    result.add(ats, "B. no icons or emoji", not GRAPHIC_CHARS.search(cv_text), "OK")
    found = [h for h in rules.section_headers if any(strip_accents(l.strip()).upper() == h for l in content)]
    result.add(
        ats,
        "C. canonical headings",
        len(found) >= rules.min_sections,
        f"{len(found)} sections",
    )
    result.add(ats, "D. date format", bool(DATE_FORMAT.search(cv_text)), "YYYY - YYYY/Present")
    bullets = [l for l in content if l.lstrip().startswith("-")]
    result.add(ats, "E. hyphen bullets", len(bullets) >= rules.min_bullets, f"{len(bullets)} bullets")
    words = len(cv_text.split())
    result.add(ats, "F. fits one page", words <= rules.max_words, f"{words} words (limit {rules.max_words})")
    longest = max((len(l) for l in lines), default=0)
    result.add(
        ats,
        "G. no overlong line",
        longest <= rules.max_line_length,
        f"longest line: {longest} chars",
    )
    return result
