# The Rejection Machine — design

**Date:** 2026-11-06
**Status:** awaiting approval
**Repo:** `KaioHomem/job-application-pipeline`

---

## Intent

A portfolio artifact for the iFood GenAI internship, AI Builder track. The
evaluator has roughly forty seconds and fifteen other portfolios queued. In
those forty seconds they should conclude two things, in this order: *this
person thinks differently*, and *this person can build*.

A funnel dashboard cannot carry that. Everyone's dashboard is bars and a donut,
and a bar chart of someone else's job hunt is not interesting to a stranger.

The thing that is interesting is the **engine**: nine filters that rejected 153
postings and wrote down why. So the artifact is not a report of what the engine
did. It is the engine, running, with the evaluator's hands on the controls.

This follows the *explorable explanation* form — Bret Victor, Nicky Case — where
the page hosts a simulation and guides the reader into poking it, rather than
plotting a result and asking them to admire it.

## The one idea

**Change the candidate, not the chart.**

Every dashboard lets you filter the data. This one lets you edit the *person*
and re-runs history. Drag the availability window and the postings are screened
again, live, in front of you: rejections flip to passes, passes flip to
rejections, and the counters move.

That single interaction converts a record of the past into a question about the
future, and it is the moment an evaluator stops scrolling.

No specific delta is promised here. Whatever the engine computes is what the
page shows.

## The corpus, and what it can honestly support

The tracker stores `date, company, role, source, url, status, next_action,
proof, notes` and nothing else. It has no `work_model`, `schedule`,
`required_tech` or `seniority`, and the facts recoverable from a note are only
the ones the firing filter happened to interpolate. A posting whose note reads
`[location] Onsite in Curitiba; outside the commutable area.` records nothing
about its shift or its stack, so **it cannot be re-screened under a different
profile**. The data was never captured.

Inventing those fields is precisely what the truth gate exists to prevent, so
the artifact runs on two datasets with different jobs:

| Dataset | Size | Source | Powers |
|---|---|---|---|
| **The record** | 189 postings | aggregated from tracker notes | Movement 1, the wall — counts and reason codes only |
| **The detailed set** | ~30 postings | hand-labelled with full fields | Movements 2 and 3 — screening and the counterfactual |

The page states both numbers plainly. Movement 3's readout is explicitly scoped
("of the 30 detailed postings, 4 more pass"), and no copy implies the
counterfactual runs over all 189.

A posting enters the detailed set only when every field it carries is a fact
about the real posting. A field that cannot be recovered keeps the posting out
of the set rather than getting a plausible value.

## Goals

1. An evaluator with no context understands the system in under forty seconds.
2. Every number on screen is recomputed in the browser from the corpus, never
   hardcoded into the markup.
3. It is visibly the same logic as `src/pipeline/screening.py`, and that claim
   is enforced by CI rather than asserted in prose.
4. It loads fast on a phone, on a Brazilian mobile connection.
5. It costs nothing to run and cannot break from an expired key or free tier.

## Non-goals

- No authentication, no accounts, no backend database.
- No LLM call inside the page. The engine is deterministic; wrapping it in a
  chat box would make it look like every other AI demo and add a key to leak.
- No scraping. The corpus is a committed, frozen snapshot.
- No real company names (see Constraints).
- No fit score. Scoring was rejected in `docs/DECISIONS.md` and the web layer
  does not reintroduce it.

## Anti-goals

Things that would make this a failure even if it shipped and worked:

- It reads as an admin panel: sidebar, KPI cards, a donut.
- It shows a number the page cannot recompute from the corpus.
- It is pretty and hollow — motion with nothing underneath.
- It implies professional experience or employment that does not exist.

## Constraints

**Company names are anonymized.** The corpus ships as `Empresa #037` plus
sector, source and role family. Reason codes, filter messages, dates and
counts are real. Publishing a permanent, searchable list of who rejected the
candidate costs him and adds nothing: the value is in the rules.

**No personal data.** The existing CI job that greps for CPF, postal code and
phone patterns covers the new directories too.

**Same repository.** `web/` and `mcp/` live beside `src/pipeline/`, because
"one engine, three surfaces" is the story and splitting repos hides it.

## Layer A — the explorable (main course)

A single static page, deployed on GitHub Pages.

### Three movements, in scroll order

**1. The wall.** Opens on the finding, not on a chart: of 153 rejected
postings, most died on location or schedule. Facts printed on the posting
itself — not skills, not experience. Stated in one sentence, with the 189
postings rendered as a field of marks that sorts itself into survivors and
casualties as the reader arrives.

A posting is attributed to **the first filter that fired on it**, in filter
order, so each one is counted exactly once and the buckets sum to 153. The
engine itself does not short-circuit — `screen()` evaluates all nine and
returns every reason — so the page says in text that it is showing the first
of possibly several.

**2. The machine.** Pick one of the preset postings, or paste a job
description and fill the parsed fields by hand. All nine filters are evaluated
and shown — the engine does not stop at the first failure, and neither does
the animation — each lighting up and printing its own `Reason`. A posting may
therefore fail on several at once, which is the truth.

The `schedule?` flag is **not** one of the nine. It comes from a separate
`FLAGS` list and only applies to a posting that already passed, so it renders
as a third state: not a pass, not a rejection, a question. An unpublished
shift is never resolved in the candidate's favour.

**3. The counterfactual.** The controls edit the profile: availability window,
accepted locations, remote, salary floor, seniority ceiling, and a toggle per
technology in the evidence list. Every change re-screens all 189 postings and
animates the deltas. A readout names the trade in plain words: *"8 more
postings pass. You would be working mornings."*

### How it is built

Static HTML, CSS and vanilla JavaScript — no framework, matching the
zero-dependency rule the Python side already keeps. Hand-written SVG for the
marks and the flow; no charting library.

**The filters are ported to JavaScript, and CI proves the port is faithful.**
A shared fixture corpus runs through the Python filters and the JavaScript
filters, and the workflow fails if any posting gets a different verdict, a
different reason code **or a different reason message**. The fixture sweeps a
grid of profiles, not just the baseline, because the profile is the thing the
page lets a visitor edit — parity that only covered one profile would be
untrue for the single interaction the artifact is built around.

This is the deliberate choice over shipping Pyodide:
a 6 MB WASM download to avoid writing 120 lines is a bad trade on a phone, and
"two implementations, one oracle, parity enforced on every push" is a better
engineering story than "we ran Python in the browser."

The 189-posting record is generated from the private tracker by a committed
anonymizer script, so the published JSON is reproducible and the mapping stays
private. The detailed set is hand-labelled and committed directly.

**The baseline profile** published with the page carries the real decision
rules — availability 12:00–22:00, remote from Brazil, one commutable city,
a salary floor, enrolled, junior ceiling — because those rules are already
disclosed to every employer the candidate applies to. It carries no address,
no contact details and no document numbers.

## Layer B — the MCP server (second surface)

The same engine exposed over the Model Context Protocol, so an evaluator can
attach it to their own Claude and interrogate the funnel in natural language.

Prior art exists — a handful of "portfolio as MCP server" projects are public —
and nearly all of them require a local install in Claude Desktop, which is the
barrier that kills them for a non-developer reviewer. This one is **hosted over
streamable HTTP**, with stdio available for developers who prefer it.

Tools:

| Tool | Answers |
|---|---|
| `funnel_summary` | counts by status and the proof-coverage figure |
| `why_skipped(code)` | the postings a given filter rejected, with their reasons |
| `simulate_profile(changes)` | re-screens the corpus under an edited profile |
| `screen_posting(fields)` | runs the nine filters over a posting the caller describes |

`simulate_profile` is the one worth having: it makes the counterfactual from
Layer A available to a language model, which means the evaluator's own
assistant can ask the question the page invites them to ask.

Layer B ships after Layer A is live. It is a second surface over the same
corpus and the same filters, not a second project.

**This departs from `docs/DECISIONS.md` #4 ("standard library only") and from
the "no backend" non-goal above, deliberately and with the owner's explicit
sign-off.** A hosted streamable-HTTP MCP server needs a running host and the
`mcp` SDK. Rather than quietly breaking a published commitment, Layer B adds a
fifth entry to `DECISIONS.md` recording the departure, what it buys (a reviewer
who is not a developer can use it) and what it costs (a host that can go down,
a dependency to keep current). The Python pipeline in `src/pipeline/` stays
standard-library only; the exception is scoped to `mcp/`.

## What success looks like

The evaluator moves a slider. If they move a slider, the artifact worked.

Secondary: the repository's CI badge is green, the parity job is visible in the
workflow list, and nothing on the page is a number a reader cannot reproduce.

## Left to the builder

- Visual direction: palette, type, the form the 189 marks take. The brief is
  "not an admin panel"; the execution is the builder's.
- Animation timing and whether the filter sequence auto-plays or is stepped.
- How a pasted job description is turned into fields: a manual form is
  acceptable for v1, and anything cleverer is a bonus.
- The exact shape of the anonymized corpus record.
- Hosting for the MCP server.
