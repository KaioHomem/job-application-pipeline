/**
 * The nine hard filters, ported from src/pipeline/screening.py.
 *
 * This file is pinned to the Python implementation by tests/fixtures/
 * parity_expected.json: CI screens the same fixture corpus with both and fails
 * on any difference in verdict, reason code or reason message. If you change a
 * rule or a sentence here, change it there in the same commit.
 */

export const SENIORITY_ORDER = [
  "intern",
  "junior",
  "mid",
  "senior",
  "staff",
  "principal",
  "manager",
];

export const FILTER_ORDER = [
  "closed",
  "affirmative",
  "location",
  "schedule",
  "seniority",
  "degree",
  "tech",
  "experience",
  "salary",
];

/** "12:00" -> 720. Minutes since midnight, so windows compare as integers. */
export function parseWindow(start, end) {
  return { start: toMinutes(start), end: toMinutes(end) };
}

function toMinutes(value) {
  const [hours, minutes] = String(value).split(":");
  return Number(hours) * 60 + Number(minutes || 0);
}

export function windowContains(outer, inner) {
  return outer.start <= inner.start && inner.end <= outer.end;
}

export function formatWindow(window) {
  const pad = (n) => String(Math.floor(n)).padStart(2, "0");
  return `${pad(window.start / 60)}:${pad(window.start % 60)}-${pad(window.end / 60)}:${pad(
    window.end % 60,
  )}`;
}

/** Python's str.capitalize(): first character up, the rest down. */
function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/** Python's format spec "g": drop trailing zeros, keep significant digits. */
function formatG(value) {
  return String(Number(value));
}

/** Python's format spec ".0f": round half to even, no decimals. */
function formatF0(value) {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) return String(floor + 1);
  if (diff < 0.5) return String(floor);
  return String(floor % 2 === 0 ? floor : floor + 1);
}

function reason(code, message) {
  return { code, message };
}

/** Normalize the raw JSON profile into the shape the filters read. */
export function normalizeProfile(raw) {
  return {
    name: raw.name,
    city: raw.city,
    state: raw.state,
    country: raw.country,
    acceptsRemote: raw.accepts_remote,
    onsiteCities: (raw.onsite_cities || []).map((c) => c.toLowerCase()),
    availability: parseWindow(raw.availability.start, raw.availability.end),
    educationStatus: raw.education.status,
    educationField: raw.education.field,
    maxSeniority: raw.max_seniority || "junior",
    minMonthlySalary: raw.min_monthly_salary ?? null,
    techYears: Object.fromEntries(
      Object.entries(raw.tech_years || {}).map(([k, v]) => [k.toLowerCase(), v]),
    ),
  };
}

/** Normalize the raw JSON posting, applying the same defaults as Job.from_dict. */
export function normalizeJob(raw) {
  return {
    company: raw.company,
    title: raw.title,
    url: raw.url,
    source: raw.source || "unknown",
    workModel: raw.work_model,
    city: raw.city ?? null,
    state: raw.state ?? null,
    country: raw.country || "Brasil",
    schedule: raw.schedule ? parseWindow(raw.schedule.start, raw.schedule.end) : null,
    seniority: raw.seniority || "junior",
    requiredTech: raw.required_tech || [],
    requiredYears: raw.required_years || {},
    requiresCompletedDegree: raw.requires_completed_degree || false,
    acceptedFields: raw.accepted_fields || [],
    monthlySalary: raw.monthly_salary ?? null,
    affirmativeOnly: raw.affirmative_only || false,
    closed: raw.closed || false,
  };
}

function yearsIn(profile, tech) {
  return profile.techYears[tech.toLowerCase()] ?? 0;
}

const FILTERS = {
  closed(job) {
    return job.closed ? reason("closed", "Posting is closed.") : null;
  },

  affirmative(job) {
    return job.affirmativeOnly
      ? reason("affirmative", "Restricted to an affirmative-action group.")
      : null;
  },

  location(job, profile) {
    const model = job.workModel.toLowerCase();
    if (model === "remote") {
      if (!profile.acceptsRemote) {
        return reason("location", "Remote, but the profile does not accept remote work.");
      }
      if (job.country.toLowerCase() !== profile.country.toLowerCase()) {
        return reason(
          "location",
          `Remote from ${job.country}; the profile works from ${profile.country}.`,
        );
      }
      return null;
    }
    const city = (job.city || "").toLowerCase();
    if (city && profile.onsiteCities.includes(city)) return null;
    const where = job.city || "an unpublished city";
    return reason("location", `${capitalize(model)} in ${where}; outside the commutable area.`);
  },

  schedule(job, profile) {
    if (job.schedule === null) return null; // handled by the schedule? flag
    if (windowContains(profile.availability, job.schedule)) return null;
    return reason(
      "schedule",
      `Shift ${formatWindow(job.schedule)} falls outside the availability window ` +
        `${formatWindow(profile.availability)}.`,
    );
  },

  seniority(job, profile) {
    const level = job.seniority.toLowerCase();
    if (!SENIORITY_ORDER.includes(level)) return null;
    if (SENIORITY_ORDER.indexOf(level) > SENIORITY_ORDER.indexOf(profile.maxSeniority)) {
      return reason(
        "seniority",
        `Posting is ${level}; the profile targets up to ${profile.maxSeniority}.`,
      );
    }
    return null;
  },

  degree(job, profile) {
    if (job.requiresCompletedDegree && profile.educationStatus !== "graduated") {
      return reason(
        "degree",
        "A completed degree is mandatory; the candidate is still enrolled.",
      );
    }
    if (job.acceptedFields.length) {
      const accepted = job.acceptedFields.map((f) => f.toLowerCase());
      if (!accepted.includes(profile.educationField.toLowerCase())) {
        return reason(
          "field",
          `Accepted fields are ${job.acceptedFields.join(", ")}; ` +
            `the candidate studies ${profile.educationField}.`,
        );
      }
    }
    return null;
  },

  tech(job, profile) {
    const missing = job.requiredTech.filter(
      (t) => !(t.toLowerCase() in profile.techYears),
    );
    if (missing.length) {
      return reason("tech", `Requires ${missing.join(", ")}; no evidence in the profile.`);
    }
    return null;
  },

  experience(job, profile) {
    const short = Object.entries(job.requiredYears)
      .filter(([tech, needed]) => yearsIn(profile, tech) < needed)
      .map(
        ([tech, needed]) =>
          `${tech} (${formatG(yearsIn(profile, tech))} of ${formatG(needed)} years)`,
      );
    if (short.length) {
      return reason("experience", `Below the required experience: ${short.join(", ")}.`);
    }
    return null;
  },

  salary(job, profile) {
    if (profile.minMonthlySalary === null || job.monthlySalary === null) return null;
    if (job.monthlySalary < profile.minMonthlySalary) {
      return reason(
        "salary",
        `Pays ${formatF0(job.monthlySalary)}; the floor is ${formatF0(profile.minMonthlySalary)}.`,
      );
    }
    return null;
  },
};

function flagUnpublishedSchedule(job) {
  return job.schedule === null
    ? reason("schedule?", "The posting does not publish a shift; confirm before applying.")
    : null;
}

/**
 * Screen one posting. Every filter runs — the chain does not short-circuit —
 * so a posting that fails on several reports all of them.
 *
 * Accepts either raw JSON or already-normalized objects.
 */
export function screen(job, profile) {
  const j = job.workModel === undefined ? normalizeJob(job) : job;
  const p = profile.acceptsRemote === undefined ? normalizeProfile(profile) : profile;

  const reasons = [];
  for (const code of FILTER_ORDER) {
    const hit = FILTERS[code](j, p);
    if (hit) reasons.push(hit);
  }
  const flags = [];
  const flag = flagUnpublishedSchedule(j);
  if (flag) flags.push(flag);

  return { job: j, reasons, flags, verdict: reasons.length ? "skip" : "pass" };
}

/** Every filter in order, whether or not it fired. Movement 2 renders this. */
export function sequence(job, profile) {
  const j = job.workModel === undefined ? normalizeJob(job) : job;
  const p = profile.acceptsRemote === undefined ? normalizeProfile(profile) : profile;
  return FILTER_ORDER.map((code) => {
    const hit = FILTERS[code](j, p);
    return { filter: code, fired: hit !== null, code: hit?.code ?? null, message: hit?.message ?? null };
  });
}
