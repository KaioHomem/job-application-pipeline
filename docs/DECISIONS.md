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

---

## 5. The MCP server breaks decision 4, on purpose

**What was decided:** `mcp_server/` depends on the `mcp` SDK and is meant to run
on a host. Decision 4 above says standard library only, and the design's own
non-goals say no backend. This is a departure, made deliberately and with the
owner's explicit sign-off, and recorded here rather than quietly committed.

**What it buys:** a reviewer who is not a developer can attach the funnel to
their own assistant and ask it questions. Every other "portfolio as an MCP
server" project found while researching this requires a local install in a
desktop client, which is exactly the barrier that makes them unused. Hosted
over streamable HTTP, there is no install.

**What it costs:** a host that can go down, a dependency to keep current, and a
decision record that no longer reads "zero dependencies" without an asterisk.
The SDK also renamed `FastMCP` to `MCPServer` in 2.x during this build, which is
the maintenance this buys in miniature.

**How the cost is contained:** the exception is scoped to `mcp_server/`.
`src/pipeline/` stays standard-library only. Everything that decides an answer
lives in `mcp_server/tools.py`, which imports nothing beyond the standard
library and the pipeline, and is unit-tested without starting a server. The SDK
appears in exactly one file, `mcp_server/server.py`, which is transport and
nothing else. If the SDK breaks or the host dies, the answers still work and
the tests still run.

---

## 6. A tool that refuses must say what was wrong

**What happened:** the first call to the hosted `screen_posting` failed. The
posting described a shift as `"13:00-22:00"`, the pipeline wants
`{"start": "13:00", "end": "22:00"}`, and the SDK turned the resulting
`TypeError` into one line: `Error executing tool screen_posting`.

The wrong shape was a fair mistake — the tool description never said which
shape it wanted. The unusable reply was the real defect. A caller who gets
`Error executing tool` has no way to find out what to send next, so it either
gives up or guesses again, and both outcomes look like the tool is broken.

**What changed:** the boundary normalizes what a caller plausibly sends — a
string, a two-element list or the canonical object all mean the same shift —
and anything it still cannot read comes back as an error that names the field
and shows a correct example. The tool descriptions now state each field's
shape rather than only its name.

`required_years` deliberately does *not* get the same leniency. A bare number
is refused, because spreading "3 years" across a technology list would invent a
requirement the posting never made, and this pipeline exists to not do that.
Leniency about shape, never about meaning.

**Where it stayed:** all of it in `mcp_server/tools.py`. `src/pipeline` keeps
one canonical shape on disk, so the parity oracle and the committed data are
untouched.

**Cost:** two normalizing functions and seven tests at the boundary, to keep
the pipeline's own input strict.
