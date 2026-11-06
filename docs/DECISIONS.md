# Design decisions

Four decisions shape this codebase. Each one cost something, and each one was
made after the cheaper alternative had already failed in a real run.

---

## 1. A filter returns a reason, not a boolean

**Alternative rejected:** `def fits(job, profile) -> bool`.

A boolean is enough to make the decision and useless everywhere after it. Two
weeks into a real run the question stops being "does this posting fit" and
becomes "why did I drop forty postings from that board, and was I right?"
With booleans the answer is gone.

So `Reason(code, message)` carries both halves: the `code` is for counting,
the `message` is for a human reading the row six weeks later. The report groups
by `code`, which is why it can state that location and schedule caused 90% of
rejections — a keyword guess over free text could never claim that honestly.

**Cost:** every filter is three lines longer and has to phrase its own refusal.

---

## 2. The gate fails, it never fixes

**Alternative rejected:** a validator that strips the offending line and
returns a cleaned CV.

Auto-repair hides the defect. The generator that wrote "5 years of experience"
will write it again next week, and the gate will quietly delete it again, and
nobody learns that the tailoring step is drifting. Worse, a gate that edits is
a gate you stop reading.

`validate()` has no write path. It prints the failing checks and the orphan
lines verbatim, and the process exits 1. A test asserts the input file is
byte-identical after a run, so the property cannot be lost by accident.

**Cost:** a failed generation is manual work instead of a silent fix.

---

## 3. "Applied" requires a file on disk

**Alternative rejected:** trusting the status column, reconciling later.

This one was not foreseen. An audit of a real run found rows marked applied
whose confirmation screen had never been archived — 26 of 27 rows cited a
proof artifact and only 16 had the captured screen stored beside them. The
funnel had quietly drifted away from what actually happened.

Reconciliation after the fact cannot repair that: once the confirmation page is
gone, the evidence is gone. So `Tracker.add` raises `ProofRequired` at write
time unless the proof path exists. An application you cannot prove is not an
application.

**Cost:** capturing proof is now mandatory before a row can be written.

---

## 4. Standard library only

**Alternative rejected:** pandas for the tracker, pydantic for the models,
rich for the output, PyYAML for the config.

Every one of those is a better tool in isolation. Together they turn a script
anybody can read and run into an environment that has to be installed, pinned
and debugged before the first line executes.

The tracker is a CSV with nine columns, the models are five dataclasses and the
config is JSON. `csv`, `dataclasses` and `json` cover all of it. `pytest` is the
only dependency, and only for the tests.

**Cost:** `report.py` formats its own columns, and configuration is JSON rather
than YAML, so comments live in `_comment` keys.

---

## What is deliberately missing

**Scoring.** No posting gets a 0-100 fit score. A score invites applying to the
73s when the honest answer is that a posting either clears the hard filters or
it does not.

**Auto-submit.** The pipeline screens, tailors, validates and records. Pressing
submit stays manual, and anything needing an account, a password, a video or a
technical test is routed to a human — those are the candidate's to answer, not
the tool's.

**Scraping.** Fetching and parsing boards is a separate concern with a separate
failure mode. This repository takes already-parsed postings.
