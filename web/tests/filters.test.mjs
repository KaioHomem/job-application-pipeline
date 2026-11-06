import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { screen, sequence, parseWindow, windowContains, FILTER_ORDER } from "../assets/filters.js";

const corpus = JSON.parse(readFileSync("tests/fixtures/parity_corpus.json", "utf8"));
const expected = JSON.parse(readFileSync("tests/fixtures/parity_expected.json", "utf8"));

function decisions() {
  const rows = [];
  for (const [name, profile] of Object.entries(corpus.profiles)) {
    for (const job of corpus.jobs) {
      const d = screen(job, profile);
      rows.push({
        profile: name,
        url: job.url,
        verdict: d.verdict,
        codes: d.reasons.map((r) => r.code),
        messages: d.reasons.map((r) => r.message),
        flags: d.flags.map((f) => f.code),
      });
    }
  }
  rows.sort((a, b) =>
    a.profile === b.profile ? (a.url < b.url ? -1 : a.url > b.url ? 1 : 0)
                            : a.profile < b.profile ? -1 : 1,
  );
  return rows;
}

test("the JS port agrees with the Python oracle on every case", () => {
  assert.deepEqual(decisions(), expected);
});

test("the oracle is not trivially empty", () => {
  assert.equal(expected.length, Object.keys(corpus.profiles).length * corpus.jobs.length);
  assert.ok(expected.some((r) => r.verdict === "pass"));
  assert.ok(expected.some((r) => r.verdict === "skip"));
});

test("the chain does not short-circuit: a bad posting reports several reasons", () => {
  const job = corpus.jobs.find((j) => j.url.endsWith("18-many-failures-at-once"));
  const d = screen(job, corpus.profiles.afternoon_student);
  assert.ok(d.reasons.length > 3, `expected several reasons, got ${d.reasons.length}`);
});

test("an unpublished shift is a flag, never a silent pass", () => {
  const job = corpus.jobs.find((j) => j.url.endsWith("14-clean-no-schedule"));
  const d = screen(job, corpus.profiles.afternoon_student);
  assert.equal(d.verdict, "pass");
  assert.ok(d.flags.some((f) => f.code === "schedule?"));
});

test("sequence reports all nine filters in order, fired or not", () => {
  const job = corpus.jobs.find((j) => j.url.endsWith("01-clean-remote-afternoon"));
  const steps = sequence(job, corpus.profiles.afternoon_student);
  assert.deepEqual(steps.map((s) => s.filter), FILTER_ORDER);
  assert.equal(steps.filter((s) => s.fired).length, 0);
});

test("window containment is inclusive at both edges", () => {
  const window = parseWindow("12:00", "22:00");
  assert.ok(windowContains(window, parseWindow("12:00", "22:00")));
  assert.ok(windowContains(window, parseWindow("13:00", "19:00")));
  assert.ok(!windowContains(window, parseWindow("09:00", "16:00")));
  assert.ok(!windowContains(window, parseWindow("20:00", "23:30")));
});

test("a seniority outside the known ladder passes silently, as in Python", () => {
  const job = corpus.jobs.find((j) => j.url.endsWith("15-unknown-seniority"));
  const d = screen(job, corpus.profiles.afternoon_student);
  assert.ok(!d.reasons.some((r) => r.code === "seniority"));
});
