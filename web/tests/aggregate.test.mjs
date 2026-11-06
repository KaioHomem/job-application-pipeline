import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { screenCorpus, delta, summarizeRecord } from "../assets/aggregate.js";

const jobs = JSON.parse(readFileSync("web/data/detailed.json", "utf8"));
const record = JSON.parse(readFileSync("web/data/record.json", "utf8"));
const baseline = JSON.parse(readFileSync("config/baseline_profile.json", "utf8"));

const mornings = { ...baseline, availability: { start: "08:00", end: "22:00" } };

test("counts always sum to the corpus size", () => {
  const r = screenCorpus(jobs, baseline);
  assert.equal(r.passed + r.skipped, r.total);
  assert.equal(r.total, jobs.length);
});

test("primary-code buckets sum to the number skipped", () => {
  const r = screenCorpus(jobs, baseline);
  const sum = Object.values(r.byPrimaryCode).reduce((a, b) => a + b, 0);
  assert.equal(sum, r.skipped);
});

test("byCode counts every reason, so it can exceed the number skipped", () => {
  const r = screenCorpus(jobs, baseline);
  const all = Object.values(r.byCode).reduce((a, b) => a + b, 0);
  const primary = Object.values(r.byPrimaryCode).reduce((a, b) => a + b, 0);
  assert.ok(all >= primary);
});

test("a posting with no published schedule is flagged, not passed silently", () => {
  const r = screenCorpus(jobs, baseline);
  const flaggedDecisions = r.decisions.filter((d) => d.flags.some((f) => f.code === "schedule?"));
  assert.equal(r.flagged, flaggedDecisions.filter((d) => d.verdict === "pass").length);
  assert.ok(r.flagged > 0, "the detailed set should contain an unpublished shift");
});

test("an inverted availability window rejects every published shift", () => {
  const inverted = { ...baseline, availability: { start: "22:00", end: "12:00" } };
  const r = screenCorpus(jobs, inverted);
  const withShift = jobs.filter((j) => j.schedule).length;
  assert.equal(r.byCode.schedule, withShift, "a window that contains nothing must reject every shift");

  // The postings that still pass are the ones with no published shift. They
  // are not a judgement that the hours fit — they carry the schedule? flag.
  for (const d of r.decisions.filter((x) => x.verdict === "pass")) {
    assert.ok(d.flags.some((f) => f.code === "schedule?"), `${d.id} passed without a shift check`);
  }
});

test("widening the window moves postings from skipped to passed", () => {
  const before = screenCorpus(jobs, baseline);
  const after = screenCorpus(jobs, mornings);
  const d = delta(before, after);
  assert.ok(d.gained.length > 0, "no posting was freed");
  assert.equal(d.net, after.passed - before.passed);
});

test("narrowing the window loses postings, and the delta says so", () => {
  const before = screenCorpus(jobs, mornings);
  const after = screenCorpus(jobs, baseline);
  assert.ok(delta(before, after).lost.length > 0);
});

test("no change produces no movement", () => {
  const r = screenCorpus(jobs, baseline);
  const d = delta(r, screenCorpus(jobs, baseline));
  assert.deepEqual(d.gained, []);
  assert.deepEqual(d.lost, []);
  assert.equal(d.net, 0);
});

test("the record summary matches the published file", () => {
  const s = summarizeRecord(record);
  assert.equal(s.total, 189);
  assert.equal(s.byStatus.applied, 27);
  assert.equal(s.skipped, 153);
  assert.equal(s.classified + s.unattributed, s.skipped);
});

test("the record's unattributed rows are counted, not hidden", () => {
  const s = summarizeRecord(record);
  assert.equal(s.byPrimaryCode.unattributed, s.unattributed);
  assert.ok(s.unattributed > 0, "the honest number is not zero and should not be rounded away");
});

test("the wall share is reported against both denominators", () => {
  const s = summarizeRecord(record);
  assert.ok(s.wallShareOfAll < s.wallShareOfClassified);
  assert.ok(s.wallShareOfAll > 0.4 && s.wallShareOfAll < 0.6);
});
