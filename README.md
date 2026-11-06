# job-application-pipeline

[![CI](https://github.com/KaioHomem/job-application-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/KaioHomem/job-application-pipeline/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Dependencies: none](https://img.shields.io/badge/dependencies-standard%20library-green)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

An auditable job-application pipeline: **screen → tailor → prove → track**.

**[The Rejection Machine →](https://kaiohomem.github.io/job-application-pipeline/)** — the engine
running in your browser. Edit the candidate's availability, locations, pay floor or seniority
ceiling, and twenty-one real postings are screened again in front of you, with the cost of the trade
named in words. The nine filters there are the ones in `src/pipeline/screening.py`, ported to
JavaScript and pinned to it by a CI job that compares sixty decisions on verdict, code and message.

A job hunt run as a build pipeline. Every posting is screened against hard
filters before any effort is spent on it, every rejection records the rule that
fired, every generated CV has to pass a gate that refuses to invent anything,
and a row cannot claim "applied" without a proof artifact on disk.

Standard library only. No network calls, no API keys, no database.

```
pip install pytest        # the only dependency, and only for the tests
export PYTHONPATH=src     # Windows: $env:PYTHONPATH = "src"

python -m pipeline screen   --profile config/profile.example.json --jobs examples/jobs.json
python -m pipeline validate --cv examples/cv_sample_pass.txt --master examples/cv_master.txt \
                            --rules config/truth_rules.example.json
python -m pipeline report   --tracker examples/tracker.sample.csv
pytest -q
```

---

## Why

Applying to jobs at volume breaks in two directions.

Apply to everything and you burn days on postings that were never possible —
a morning shift against afternoon classes, a framework you have never touched,
an onsite role in another state. Apply carefully and the volume collapses.

The expensive part is not filling the form. It is deciding, consistently, which
postings deserve a form at all, and then being able to say later *why* a
posting was dropped. A rejection with no recorded reason cannot be reviewed,
and a rule you cannot review is a rule you will contradict next week.

The second failure mode is worse. A CV generator that tailors itself to a
posting will, left unsupervised, start agreeing with the posting — a year of
experience here, a framework there, a percentage that nobody measured. Those
edits pass a human skim and fail an interview.

So this pipeline has two opinions, and they are the whole point:

**Every "no" carries its reason.** Filters return a code and a sentence, both
persisted to the tracker. The funnel report groups by the code the filter
emitted, not by a keyword guess over free text, so the report says which rule
did the work.

**The gate never fixes anything.** The truth gate fails a CV and prints why. It
has no authority to rewrite the document, because a validator that silently
repairs its input teaches you nothing about the generator that produced the
problem — and the next variant will reproduce it.

## Running it for real

Measured on a private run of this pipeline between 2026-09-08 and 2026-09-24,
seven active days. The tracker and profile behind these numbers are personal
data and are not in this repository.

| | |
|---|---|
| Postings triaged | **189** |
| Applications submitted | **27** |
| Rejected by a hard filter, reason recorded | **153** |
| Stopped for a human (account creation, video, technical test) | **7** |

What rejected those 153, as far as the data can say:

| Reason | Count |
|---|---|
| Location — onsite or hybrid outside the commutable area | 60 |
| **Not attributable** — the note does not name a filter | 39 |
| Central technology with no evidence in the profile | 19 |
| Schedule — shift collides with the availability window | 19 |
| Required professional experience above the profile | 6 |
| Field of study not accepted | 4 |
| Restricted to an affirmative-action group | 3 |
| Closed or expired posting | 2 |
| Completed degree required | 1 |

**Read that table with its caveat.** Most of these rows predate the bracketed
reason codes, so their reason is Portuguese prose and the bucket is *derived*
by the keyword rules in `scripts/anonymize_corpus.py`, not emitted by a filter.
The published record marks each row `recorded` or `classified` so the two are
never conflated, and 39 rows resisted classification rather than being forced
into a bucket. An earlier draft of this README reported 113 and 25 for the top
two rows and claimed they were 90% of the work; that came from a looser pattern
where the bare substring `local` matched notes like "local de trabalho", and
it was wrong.

Two findings worth more than the totals:

**Location and schedule still lead, at 79 of 153.** Not skills. Roughly half of
all rejections — and 69% of the ones that could be attributed at all — came
down to facts printed on the posting itself, which is exactly the filtering a
human does badly at volume and stops doing by posting forty.

**The unattributable 39 are why the tracker now records codes.** A reason kept
only as prose cannot be counted later. `Reason(code, message)` exists because
of this table.

**The proof rule exists because an audit found drift.** Of the 27 applications,
26 cite a proof artifact and 16 have a captured confirmation screen stored
beside the row. That gap — rows marked applied whose evidence was never
archived — is what `ProofRequired` in `tracker.py` now prevents at write time.
It was written after the audit, not before it.

## How it fits together

```
postings ──► screening.py ──► skip + reason ──► tracker.csv
                   │
                   └─ pass ──► tailor ──► truth_gate.py ──► reject + failing checks
                                              │
                                              └─ approved ──► submit ──► proof file
                                                                            │
                                                            tracker.csv ◄───┘
                                                                  │
                                                            report.py ──► funnel
```

| Module | What it owns |
|---|---|
| `models.py` | `Profile`, `Job`, `TimeWindow`. Loaded from JSON; time windows compare as integers. |
| `screening.py` | Nine hard filters. Each returns `None` or a `Reason(code, message)`. |
| `truth_gate.py` | Five truth checks and seven ATS checks over the generated CV text. |
| `tracker.py` | CSV rows, deduplication by URL, and the proof requirement. |
| `report.py` | Funnel, skip reasons by code, proof coverage. |
| `cli.py` | `screen`, `validate`, `report`. |

### Filters

`closed`, `affirmative`, `location`, `schedule`, `seniority`, `degree`,
`tech_evidence`, `experience_years`, `salary`.

Filters are conservative about what a posting does not say. An unpublished
shift is **not** assumed to fit: it passes the filter and raises a
`schedule?` flag so a human confirms before applying. Guessing in the
candidate's favour is how you end up in an interview for a 9-to-6.

`tech_evidence` is the one that keeps the rest honest. A role built on a
framework absent from the profile is a hard stop, not a stretch — there is no
version of that interview that goes well.

### The truth gate

| Check | Fails when |
|---|---|
| contained in master | a line in the variant traces back to no line in the master CV |
| no unsupported claims | seniority terms, aggregated years, invented metrics, uncertified language levels, tooling the master never mentions |
| degree marked in progress | an enrolled candidate's CV reads as graduated |
| only confirmed skills | a skill line lists something outside the confirmed set |
| ATS gate | layout tables, emoji, missing canonical headings, bad date format, too few bullets, over one page, overlong lines |

Containment is the load-bearing one. Tailoring may reorder, translate, select
and drop. It may never add. Anything the variant says that the master does not
is reported as an orphan line, with the text, so you can see what the generator
tried to get away with.

```
$ python -m pipeline validate --cv examples/cv_sample_fail.txt ...

TRUTH GATE
  [PASS] 1. text extraction           24 content lines
  [FAIL] 2. contained in master       11 orphan line(s): ['Senior backend engineer with 5 years...']
  [FAIL] 3. no unsupported claims     aggregated professional experience; invented monetary figure;
                                      invented percentage metric; seniority term the candidate cannot claim
  [FAIL] 4. degree marked in progress missing
  [FAIL] 5. only confirmed skills     outside the confirmed list: ['go', 'rust', 'oracle', 'salesforce']

RESULT: REJECTED (8/12 checks passed)
```

Exit code 1. Nothing was edited.

## Configuration

Two JSON files, both with a committed example and neither containing real data.

- `config/profile.example.json` — availability window, locations, education,
  seniority ceiling, salary floor, and `tech_years`. A `0` there means academic
  or self-directed practice with no professional experience, and that is the
  number a form gets told.
- `config/truth_rules.example.json` — canonical section headings, the confirmed
  skill list, and the blocked patterns. Every blocked pattern is there because
  a generator once produced that exact claim.

## Tests

31 tests, `pytest -q`. They cover each filter rejecting for its own reason,
`TimeWindow` containment at the boundaries, the gate approving a legitimate
variant and rejecting an inflated one, orphan-line detection, the proof
requirement, duplicate submission, and a check that the gate leaves its input
byte-identical.

## Scope

This repository is the decision core, written to be read: screening, the truth
gate, the tracker and the report.

Browser automation, PDF rendering and job-board scraping belong to the private
operational layer and are not here. That layer also integrates a third-party
application engine ([privacydied/job-application-skill](https://github.com/privacydied/job-application-skill));
none of its code is in this repository.

The reasoning behind the four decisions that shape this code — coded reasons,
a gate that never repairs, the proof requirement and the zero-dependency rule —
is written up in [docs/DECISIONS.md](docs/DECISIONS.md), including what each
one cost.

Built with AI assistance — that is how I work, and the commit history shows it.

## License

MIT. See [LICENSE](LICENSE).
