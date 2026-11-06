/**
 * Screening the whole detailed set, and diffing two runs of it.
 *
 * Movement 3 lives on `delta`: the visitor edits the profile, both runs are
 * compared, and the page states the trade in words. Nothing here is cached —
 * 21 postings times nine filters is nothing, and a stale count is worse than
 * a recomputed one.
 */

import { screen, normalizeJob, normalizeProfile } from "./filters.js";

/** Screen every posting under one profile. */
export function screenCorpus(jobs, rawProfile) {
  const profile = normalizeProfile(rawProfile);
  const decisions = jobs.map((raw) => {
    const job = normalizeJob({
      ...raw,
      company: raw.id,
      url: raw.url ?? `urn:posting:${raw.id}:${raw.title}`,
    });
    const decision = screen(job, profile);
    return { id: raw.id, title: raw.title, roleFamily: raw.role_family, ...decision };
  });

  const byCode = {};
  const byPrimaryCode = {};
  let passed = 0;
  let flagged = 0;

  for (const d of decisions) {
    if (d.verdict === "pass") {
      passed += 1;
      if (d.flags.length) flagged += 1;
    } else {
      // Every code that fired, so a posting blocked three ways is counted
      // three times here...
      for (const r of d.reasons) byCode[r.code] = (byCode[r.code] || 0) + 1;
      // ...and once here, under the first filter that stopped it, so these
      // buckets sum to the number skipped.
      const first = d.reasons[0].code;
      byPrimaryCode[first] = (byPrimaryCode[first] || 0) + 1;
    }
  }

  return {
    total: decisions.length,
    passed,
    skipped: decisions.length - passed,
    flagged,
    byCode,
    byPrimaryCode,
    decisions,
  };
}

/** What changed between two runs over the same postings. */
export function delta(before, after) {
  const was = new Map(before.decisions.map((d) => [d.id + d.title, d.verdict]));
  const gained = [];
  const lost = [];

  for (const d of after.decisions) {
    const previous = was.get(d.id + d.title);
    if (previous === "skip" && d.verdict === "pass") gained.push(d);
    if (previous === "pass" && d.verdict === "skip") lost.push(d);
  }

  const byCode = {};
  for (const code of new Set([...Object.keys(before.byPrimaryCode), ...Object.keys(after.byPrimaryCode)])) {
    byCode[code] = (after.byPrimaryCode[code] || 0) - (before.byPrimaryCode[code] || 0);
  }

  return { gained, lost, net: gained.length - lost.length, byCode };
}

/**
 * Aggregate the 189-posting record. This one is counted, never re-screened:
 * the tracker never stored the fields a filter needs.
 */
export function summarizeRecord(records) {
  const byStatus = {};
  const byPrimaryCode = {};
  const bySource = {};
  let classified = 0;

  for (const r of records) {
    byStatus[r.status] = (byStatus[r.status] || 0) + 1;
    bySource[r.source] = (bySource[r.source] || 0) + 1;
    if (r.status !== "skipped") continue;
    const bucket = r.primary_code ?? "unattributed";
    byPrimaryCode[bucket] = (byPrimaryCode[bucket] || 0) + 1;
    if (r.code_source) classified += 1;
  }

  const skipped = byStatus.skipped || 0;
  const wall = (byPrimaryCode.location || 0) + (byPrimaryCode.schedule || 0);

  return {
    total: records.length,
    byStatus,
    bySource,
    byPrimaryCode,
    skipped,
    classified,
    unattributed: skipped - classified,
    wall,
    wallShareOfAll: skipped ? wall / skipped : 0,
    wallShareOfClassified: classified ? wall / classified : 0,
  };
}
