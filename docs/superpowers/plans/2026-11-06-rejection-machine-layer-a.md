# The Rejection Machine — Layer A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a static page where a visitor edits the candidate profile and watches all 189 postings get re-screened live by the same nine filters that run in Python.

**Architecture:** The nine filters are ported to vanilla JavaScript. A shared fixture corpus is screened by both implementations and compared against one committed expected-decisions file, so CI fails the moment the port drifts from `src/pipeline/screening.py`. An anonymizer turns the private tracker into a committed `corpus.json`. The page is three scroll movements over a pure aggregation function.

**Tech Stack:** Python 3.11+ stdlib + pytest (existing), vanilla JS with `node:test`, hand-written SVG, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-11-06-funnel-explorable-design.md`

Layer B (MCP server) is a separate plan, written after this one ships.

## Global Constraints

- No JS framework and no charting library. Hand-written SVG only.
- No LLM call anywhere in the page. The engine is deterministic.
- Python side stays standard library only; `pytest` remains the sole dev dependency.
- JS tests use `node:test` and `node:assert`. No npm dependencies, no `package.json` beyond `{"type": "module"}`.
- Company names never appear in committed data. Records carry `Empresa #NNN`, sector, source, role family.
- Reason codes are exactly: `closed`, `affirmative`, `location`, `schedule`, `seniority`, `degree`, `field`, `tech`, `experience`, `salary`, plus the flag `schedule?`.
- No fit score anywhere — `docs/DECISIONS.md` rejected scoring and the web layer must not reintroduce it.
- Every figure rendered must be computed from `corpus.json` at runtime; no number hardcoded in markup.
- The existing `no-personal-data` CI job must keep passing over the new directories.

## Review Focus

1. **A posting with no published schedule** must render as a flag, never as a silent pass — the spec calls this out and it is the easiest thing to get wrong. Test in Task 4.
2. **A profile window where start >= end** (slider dragged past itself) must not make every posting pass. Test in Task 4.
3. **`corpus.json` failing to load** must show an explicit error, not an empty page reading `0 postings` as if that were the finding. Test in Task 5.
4. **A pasted posting missing required fields** must report which field is missing rather than throwing. Test in Task 6.
5. **`prefers-reduced-motion: reduce`** must disable the filter animation and jump to the final state. Test in Task 7.

---

### Task 1: Parity corpus and the Python oracle

**Files:**
- Create: `tests/fixtures/parity_corpus.json`
- Create: `scripts/gen_parity_expected.py`
- Create: `tests/fixtures/parity_expected.json` (generated, committed)
- Test: `tests/test_parity.py`

**Interfaces:**
- Produces: `parity_corpus.json` with shape `{"profiles": {<name>: <Profile JSON>}, "jobs": [<Job JSON>]}`, using the field names `Profile.load` and `Job.from_dict` already accept.
- Produces: `parity_expected.json` as a list of `{"profile": str, "url": str, "verdict": "pass"|"skip", "codes": [str], "flags": [str]}`, sorted by `(profile, url)`.
- Produces: `scripts/gen_parity_expected.py` exposing `build_expected(corpus: dict) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parity.py
import json
from scripts.gen_parity_expected import build_expected

def test_committed_expectations_match_the_python_filters():
    corpus = json.load(open("tests/fixtures/parity_corpus.json", encoding="utf-8"))
    committed = json.load(open("tests/fixtures/parity_expected.json", encoding="utf-8"))
    assert build_expected(corpus) == committed

def test_corpus_exercises_every_reason_code():
    corpus = json.load(open("tests/fixtures/parity_corpus.json", encoding="utf-8"))
    seen = {c for row in build_expected(corpus) for c in row["codes"]}
    assert seen == {"closed", "affirmative", "location", "schedule", "seniority",
                    "degree", "field", "tech", "experience", "salary"}

def test_corpus_exercises_the_schedule_flag():
    corpus = json.load(open("tests/fixtures/parity_corpus.json", encoding="utf-8"))
    assert any("schedule?" in row["flags"] for row in build_expected(corpus))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_parity.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Write `tests/fixtures/parity_corpus.json`**

At least three profiles (one matching `config/profile.example.json`, one that accepts mornings, one that refuses remote) and enough jobs that every code in the second test fires at least once, plus one job with `"schedule": null` and one job that passes all nine filters.

- [ ] **Step 4: Implement `build_expected(corpus: dict) -> list[dict]` in `scripts/gen_parity_expected.py`**

Loads each profile through `Profile`, each job through `Job.from_dict`, calls `screen`, and emits the sorted record shape above. Add a `__main__` block that writes `tests/fixtures/parity_expected.json` with `indent=2` and a trailing newline.

- [ ] **Step 5: Generate the expected file**

Run: `python scripts/gen_parity_expected.py`
Expected: writes `tests/fixtures/parity_expected.json`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_parity.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures scripts/gen_parity_expected.py tests/test_parity.py
git commit -m "test: pin the Python filters to a committed decision oracle"
```

---

### Task 2: JavaScript port of the filters, with CI parity

**Files:**
- Create: `web/assets/filters.js`
- Create: `web/package.json` (`{"type": "module"}` only)
- Test: `web/tests/filters.test.mjs`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `tests/fixtures/parity_corpus.json` and `tests/fixtures/parity_expected.json` from Task 1.
- Produces: `screen(job, profile) -> {verdict, reasons, flags}` where `reasons` and `flags` are `{code, message}` arrays, plus `parseWindow(str) -> {start, end}` and `windowContains(outer, inner) -> boolean`.
- Message strings must match `src/pipeline/screening.py` byte for byte; only `codes` and `verdict` are compared by the parity test, but Task 6 renders the messages.

- [ ] **Step 1: Write the failing test**

```js
// web/tests/filters.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { screen } from "../assets/filters.js";

const corpus = JSON.parse(readFileSync("tests/fixtures/parity_corpus.json", "utf8"));
const expected = JSON.parse(readFileSync("tests/fixtures/parity_expected.json", "utf8"));

test("the JS port agrees with the Python oracle on every case", () => {
  const actual = [];
  for (const [name, profile] of Object.entries(corpus.profiles)) {
    for (const job of corpus.jobs) {
      const d = screen(job, profile);
      actual.push({ profile: name, url: job.url, verdict: d.verdict,
                    codes: d.reasons.map(r => r.code), flags: d.flags.map(f => f.code) });
    }
  }
  actual.sort((a, b) => (a.profile + a.url).localeCompare(b.profile + b.url));
  assert.deepEqual(actual, expected);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/tests/`
Expected: FAIL, cannot find `../assets/filters.js`

- [ ] **Step 3: Implement the nine filters in `web/assets/filters.js`**

Port `closed`, `affirmative`, `location`, `schedule`, `seniority`, `degree`, `tech_evidence`, `experience_years`, `salary` and the `schedule?` flag from `src/pipeline/screening.py`, preserving filter order and message text. Export `screen`, `parseWindow`, `windowContains`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test web/tests/`
Expected: 1 pass

- [ ] **Step 5: Add the parity job to CI**

In `.github/workflows/ci.yml`, add a `parity` job on `ubuntu-latest` that checks out, runs `actions/setup-node@v4` with Node 20, runs `python scripts/gen_parity_expected.py`, fails if `git diff --exit-code tests/fixtures/parity_expected.json` reports changes, then runs `node --test web/tests/`.

- [ ] **Step 6: Commit**

```bash
git add web/assets/filters.js web/package.json web/tests .github/workflows/ci.yml
git commit -m "feat(web): port the nine filters to JS with CI-enforced parity"
```

---

### Task 3: The record — anonymizer for the 189

**Files:**
- Create: `scripts/anonymize_corpus.py`
- Create: `web/data/record.json` (generated, committed)
- Test: `tests/test_anonymize.py`

The tracker cannot support re-screening (it stores no `work_model`, `schedule`,
`required_tech` or `seniority`), so this task produces the **aggregate record
only**: counts and reason codes for Movement 1. The re-screenable detailed set
is Task 3b. Nothing here may invent a field the tracker does not contain.

**Interfaces:**
- Produces: `anonymize(rows: list[dict]) -> list[dict]` emitting `{"id": "Empresa #037", "role_family": str, "source": str, "date": str, "status": str, "codes": [str], "primary_code": str|None, "messages": [str]}`.
- `primary_code` is the first code in the note, which is the first filter that fired; it is what Movement 1 counts so the buckets sum to the skipped total.
- `role_family` is one of `estagio`, `suporte`, `dados`, `dev`, `qa`, `outro`, derived from the role title.
- The same company name maps to the same id within one run and the mapping is never written to disk.

- [ ] **Step 1: Write the failing test**

```python
def test_company_names_never_survive():
    rows = [{"Company": "Instituto Eldorado", "Role": "Estagio Web", "Source": "gupy",
             "Date": "2026-09-08", "Status": "Rejected", "Notes": "[location] Onsite in Campinas."}]
    out = anonymize(rows, salt="x")
    assert "Eldorado" not in json.dumps(out)
    assert out[0]["id"].startswith("Empresa #")

def test_the_same_company_gets_the_same_id():
    rows = [{...}, {...}]  # two rows, one company
    out = anonymize(rows, salt="x")
    assert out[0]["id"] == out[1]["id"]

def test_reason_codes_are_extracted_from_notes():
    out = anonymize([{..., "Notes": "[schedule] Shift 09:00-16:00 ..."}], salt="x")
    assert out[0]["codes"] == ["schedule"]

def test_role_family_is_classified():
    assert anonymize([{..., "Role": "Analista de Suporte Junior"}], salt="x")[0]["role_family"] == "suporte"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_anonymize.py -v`
Expected: FAIL, import error

- [ ] **Step 3: Implement `anonymize` in `scripts/anonymize_corpus.py`**

Company ids come from a stable sort of distinct company names, numbered from 1 and zero-padded to three digits. Reason codes reuse the `\[([a-z?]+)\]` pattern already in `src/pipeline/report.py`. Add a `__main__` block taking `--tracker` and `--out`, defaulting `--out` to `web/data/corpus.json`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_anonymize.py -v`
Expected: 4 passed

- [ ] **Step 5: Generate the record from the private tracker**

Run: `python scripts/anonymize_corpus.py --tracker <private tracker path> --out web/data/record.json`
Expected: 189 records, no company name present.

- [ ] **Step 6: Commit**

```bash
git add scripts/anonymize_corpus.py tests/test_anonymize.py web/data/record.json
git commit -m "feat: anonymize the tracker into a publishable record"
```

---

### Task 3b: The detailed set — hand-labelled, re-screenable postings

**Files:**
- Create: `web/data/detailed.json`
- Create: `config/baseline_profile.json`
- Test: `tests/test_detailed_set.py`

Every posting here carries the full `Job` field set so it can be re-screened
under an edited profile. A posting is included only when every field is a fact
about the real posting; a field that cannot be recovered keeps the posting out
of the set rather than receiving a plausible value.

**Interfaces:**
- Produces: `web/data/detailed.json` as a list of `Job`-shaped dicts, each with an added `"id": "Empresa #NNN"` matching the record from Task 3 and a `"recovered_from"` field naming the evidence (`"posting still live"`, `"archived note"`, `"proof artifact"`).
- Produces: `config/baseline_profile.json`, the published profile: real decision rules, no address, no contact details, no document numbers.

- [ ] **Step 1: Write the failing test**

```python
def test_every_detailed_posting_loads_as_a_job():
    for raw in json.load(open("web/data/detailed.json", encoding="utf-8")):
        Job.from_dict(raw)

def test_no_company_names_in_the_detailed_set():
    text = open("web/data/detailed.json", encoding="utf-8").read()
    assert re.fullmatch(r'Empresa #\d{3}', ...) # every id matches
    for name in KNOWN_COMPANY_NAMES:  # read from the private tracker at test time
        assert name not in text

def test_every_posting_declares_its_evidence():
    for raw in json.load(open("web/data/detailed.json", encoding="utf-8")):
        assert raw["recovered_from"] in {"posting still live", "archived note", "proof artifact"}

def test_the_baseline_profile_carries_no_contact_details():
    raw = json.load(open("config/baseline_profile.json", encoding="utf-8"))
    assert not {"email", "phone", "address", "cpf"} & raw.keys()
    Profile.load("config/baseline_profile.json")

def test_the_detailed_set_exercises_several_outcomes():
    jobs = [Job.from_dict(r) for r in json.load(open("web/data/detailed.json", encoding="utf-8"))]
    profile = Profile.load("config/baseline_profile.json")
    verdicts = {screen(j, profile).verdict for j in jobs}
    assert verdicts == {"pass", "skip"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_detailed_set.py -v`
Expected: FAIL, `web/data/detailed.json` missing

- [ ] **Step 3: Label the postings**

Work through the tracker rows whose posting is still reachable or whose note
and proof artifact together pin every field. Target roughly 30. Record
`recovered_from` per posting. Leave out anything that would need a guess.

- [ ] **Step 4: Write `config/baseline_profile.json`**

Same shape `Profile.load` accepts, carrying the real rules and nothing
identifying beyond the commutable city.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_detailed_set.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add web/data/detailed.json config/baseline_profile.json tests/test_detailed_set.py
git commit -m "feat: hand-labelled detailed set that can actually be re-screened"
```

---

### Task 4: Aggregation layer

**Files:**
- Create: `web/assets/aggregate.js`
- Test: `web/tests/aggregate.test.mjs`

**Interfaces:**
- Consumes: `screen` from Task 2, `corpus.json` from Task 3.
- Produces: `screenCorpus(jobs, profile) -> {total, passed, skipped, byCode: {code: n}, flagged: n, decisions: []}` and `delta(before, after) -> {gained: [url], lost: [url], byCode: {code: n}}`.

- [ ] **Step 1: Write the failing test**

```js
test("a posting with no published schedule is flagged, not passed silently", () => {
  const r = screenCorpus([jobWithNullSchedule], profile);
  assert.equal(r.flagged, 1);
  assert.ok(r.decisions[0].flags.some(f => f.code === "schedule?"));
});

test("an inverted availability window passes nothing on schedule", () => {
  const r = screenCorpus(jobs, { ...profile, availability: { start: "22:00", end: "12:00" } });
  assert.equal(r.byCode.schedule > 0, true);
});

test("widening the window moves postings from skipped to passed", () => {
  const before = screenCorpus(jobs, profile);
  const after = screenCorpus(jobs, { ...profile, availability: { start: "08:00", end: "22:00" } });
  assert.ok(delta(before, after).gained.length > 0);
});

test("counts always sum to the corpus size", () => {
  const r = screenCorpus(jobs, profile);
  assert.equal(r.passed + r.skipped, r.total);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/tests/`
Expected: FAIL on the missing module

- [ ] **Step 3: Implement `screenCorpus` and `delta` in `web/assets/aggregate.js`**

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test web/tests/`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add web/assets/aggregate.js web/tests/aggregate.test.mjs
git commit -m "feat(web): aggregation and delta over the corpus"
```

---

### Task 5: Page shell and movement 1 — the wall

**Files:**
- Create: `web/index.html`, `web/assets/style.css`, `web/assets/app.js`
- Test: `web/tests/load.test.mjs`

**Interfaces:**
- Consumes: `screenCorpus` from Task 4.
- Produces: `loadCorpus(fetchFn) -> Promise<{jobs}>` which rejects with a message naming the file when the response is not ok.

- [ ] **Step 1: Write the failing test**

```js
test("a missing corpus reports an error instead of resolving to zero postings", async () => {
  await assert.rejects(() => loadCorpus(async () => ({ ok: false, status: 404 })),
                       /corpus\.json/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/tests/`

- [ ] **Step 3: Implement `loadCorpus` in `web/assets/app.js` and build the first movement**

`index.html` carries one `<main>` with three `<section>` landmarks. Movement 1 renders all 189 postings as SVG marks that settle into survivors and casualties, with the headline figure (138 of 153 lost to location or schedule) computed from the corpus, never written into the HTML. A visible error region shows the `loadCorpus` rejection message.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test web/tests/`

- [ ] **Step 5: Check it in a browser at 375px and 1440px wide**

Expected: no horizontal scroll, the headline figure matches `python -m pipeline report`.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/assets/style.css web/assets/app.js web/tests/load.test.mjs
git commit -m "feat(web): page shell and the wall"
```

---

### Task 6: Movement 2 — the machine

**Files:**
- Create: `web/assets/machine.js`, `web/data/presets.json`
- Modify: `web/index.html`, `web/assets/app.js`
- Test: `web/tests/machine.test.mjs`

**Interfaces:**
- Consumes: `screen` from Task 2.
- Produces: `postingFromForm(fields) -> {job}` throwing `MissingField` naming the first absent required field, and `sequence(job, profile) -> [{code, fired, message}]` in filter order.

- [ ] **Step 1: Write the failing test**

```js
test("a posting missing a required field names the field", () => {
  assert.throws(() => postingFromForm({ title: "Estagio" }), /work_model/);
});

test("the sequence reports every filter in order, fired or not", () => {
  const steps = sequence(job, profile);
  assert.equal(steps.length, 9);
  assert.equal(steps[0].code, "closed");
});

test("a surviving posting fires nothing", () => {
  assert.equal(sequence(passingJob, profile).filter(s => s.fired).length, 0);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/tests/`

- [ ] **Step 3: Implement `postingFromForm` and `sequence` in `web/assets/machine.js`, and wire the UI**

The nine filters light up in order, each printing its own `Reason.message`. `web/data/presets.json` holds three anonymized postings from the corpus, one of which survives. The `schedule?` flag renders in its own style, distinct from both pass and skip.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test web/tests/`

- [ ] **Step 5: Commit**

```bash
git add web/assets/machine.js web/data/presets.json web/index.html web/assets/app.js web/tests/machine.test.mjs
git commit -m "feat(web): the machine, nine filters firing in sequence"
```

---

### Task 7: Movement 3 — the counterfactual

**Files:**
- Create: `web/assets/controls.js`
- Modify: `web/index.html`, `web/assets/app.js`, `web/assets/style.css`
- Test: `web/tests/controls.test.mjs`

**Interfaces:**
- Consumes: `screenCorpus` and `delta` from Task 4.
- Produces: `profileFromControls(state) -> Profile` and `tradeSentence(before, after, state) -> string`.

- [ ] **Step 1: Write the failing test**

```js
test("the trade sentence names the gain and its cost", () => {
  const s = tradeSentence(before, after, { availability: { start: "08:00", end: "18:00" } });
  assert.match(s, /8 more postings pass/);
  assert.match(s, /mornings/);
});

test("no change produces no claim of gain", () => {
  assert.doesNotMatch(tradeSentence(before, before, state), /more postings pass/);
});

test("reduced motion skips straight to the final state", () => {
  assert.equal(animationDuration({ reducedMotion: true }), 0);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/tests/`

- [ ] **Step 3: Implement the controls**

Sliders for the availability window, salary floor and seniority ceiling; toggles for remote, each onsite city, and each technology in the evidence list. Every change re-runs `screenCorpus` over all 189 postings and animates the deltas. Honour `prefers-reduced-motion: reduce` by jumping to the final state.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test web/tests/`

- [ ] **Step 5: Commit**

```bash
git add web/assets/controls.js web/index.html web/assets/app.js web/assets/style.css web/tests/controls.test.mjs
git commit -m "feat(web): edit the candidate and re-run history"
```

---

### Task 8: Deploy

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: Add the Pages deploy job**

A `deploy` job gated on `needs: [test, parity, no-personal-data]` and `github.ref == 'refs/heads/main'`, using `actions/upload-pages-artifact@v3` with `path: web` and `actions/deploy-pages@v4`, with `permissions: {pages: write, id-token: write}`.

- [ ] **Step 2: Push and confirm the deployment**

Run: `git push`
Expected: the workflow succeeds and the Pages URL serves the page.

- [ ] **Step 3: Link it from the README**

Put the live URL in the first screenful, above the usage block, with one line saying the visitor can edit the profile and re-screen all 189 postings.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: publish the explorable to GitHub Pages"
```
