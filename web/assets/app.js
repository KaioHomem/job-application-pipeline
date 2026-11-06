/**
 * Page wiring. Every figure rendered here is computed from the published data;
 * none is written into the markup.
 */

import { screenCorpus, delta, summarizeRecord } from "./aggregate.js";
import { sequence } from "./filters.js";

const dotFired =
  '<svg width="11" height="11" viewBox="0 0 11 11"><rect width="11" height="11" rx="1.5" fill="currentColor"/></svg>';
const dotClear =
  '<svg width="11" height="11" viewBox="0 0 11 11"><rect x="1" y="1" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="2"/></svg>';

const FILTER_LABELS = {
  closed: "closed",
  affirmative: "affirmative",
  location: "location",
  schedule: "schedule",
  seniority: "seniority",
  degree: "degree",
  tech: "technology",
  experience: "experience",
  salary: "pay",
};

const BUCKET_LABELS = {
  location: "Where the work is",
  schedule: "When the shift runs",
  tech: "A technology with no evidence",
  experience: "Professional years required",
  field: "Field of study not accepted",
  affirmative: "Reserved for a group",
  closed: "Already closed",
  degree: "A finished degree required",
  salary: "Below the pay floor",
  unattributed: "Reason kept only as prose",
};

const BUCKET_COLOURS = {
  location: "#8a4b32",
  schedule: "#b2764f",
  tech: "#6b6763",
  experience: "#8d8579",
  field: "#a09585",
  affirmative: "#b3aa9c",
  closed: "#c3bbae",
  degree: "#cdc3b6",
  salary: "#d6ccc0",
  unattributed: "#e0d8cd",
  applied: "#5c6b54",
  needs_human_action: "#9fae95",
  rejected: "#43423f",
};

export async function loadJSON(path, fetchFn = fetch) {
  const response = await fetchFn(path);
  if (!response.ok) {
    throw new Error(`could not load ${path} (${response.status})`);
  }
  return response.json();
}

/* ------------------------------------------------------------ movement 1 */

function drawField(svg, record, summary) {
  const order = [
    ...Object.keys(summary.byPrimaryCode).sort(
      (a, b) => summary.byPrimaryCode[b] - summary.byPrimaryCode[a],
    ),
  ];
  const groups = order.map((code) => ({
    key: code,
    label: BUCKET_LABELS[code] || code,
    count: summary.byPrimaryCode[code],
    colour: BUCKET_COLOURS[code] || "#b3aa9c",
  }));
  for (const status of ["applied", "needs_human_action", "rejected"]) {
    if (summary.byStatus[status]) {
      groups.push({
        key: status,
        label:
          status === "applied"
            ? "Applied, with proof"
            : status === "rejected"
              ? "Answered, not selected"
              : "Stopped for a human",
        count: summary.byStatus[status],
        colour: BUCKET_COLOURS[status],
      });
    }
  }

  const COLS = 19;
  const CELL = 40;
  const SIZE = 30;
  let index = 0;
  const marks = [];

  for (const group of groups) {
    for (let i = 0; i < group.count; i += 1) {
      const x = (index % COLS) * CELL;
      const y = Math.floor(index / COLS) * CELL;
      marks.push(
        `<rect x="${x}" y="${y}" width="${SIZE}" height="${SIZE}" fill="${group.colour}">` +
          `<title>${group.label}</title></rect>`,
      );
      index += 1;
    }
  }

  const rows = Math.ceil(index / COLS);
  svg.setAttribute("viewBox", `0 0 ${COLS * CELL - (CELL - SIZE)} ${rows * CELL - (CELL - SIZE)}`);
  svg.insertAdjacentHTML("beforeend", marks.join(""));
  return groups;
}

function renderLegend(node, groups, total) {
  node.innerHTML = groups
    .map(
      (g) =>
        `<div><span style="background:${g.colour}"></span>` +
        `<dt style="display:contents">${g.label}</dt>` +
        `<dd style="display:contents"><b>${g.count}</b></dd></div>`,
    )
    .join("");
  return total;
}

/* ------------------------------------------------------------ movement 2 */

function renderChain(job, profile, nodes) {
  const steps = sequence(
    { ...job, company: job.id, url: `urn:posting:${job.id}` },
    profile,
  );
  nodes.chain.innerHTML = steps
    .map(
      (s) =>
        `<li data-state="${s.fired ? "fired" : "clear"}">` +
        `<span class="chain__dot" aria-hidden="true">${s.fired ? dotFired : dotClear}</span>` +
        `<span class="chain__name">${FILTER_LABELS[s.filter]}</span>` +
        `<span class="chain__msg">${s.message ? s.message : "clear"}</span></li>`,
    )
    .join("");

  const fired = steps.filter((s) => s.fired);
  nodes.verdict.dataset.verdict = fired.length ? "skip" : "pass";
  nodes.verdict.innerHTML = fired.length
    ? `<b>Refused.</b> <span>${fired.length} of nine filters fired, and all of them are recorded.</span>`
    : `<b>Survives.</b> <span>No filter fired. This one reaches a human.</span>`;

  const unpublished = !job.schedule;
  nodes.flagline.hidden = !unpublished;
  if (unpublished) {
    nodes.flagline.textContent =
      "Flag: the posting does not publish a shift. Not resolved in my favour — confirm before applying.";
  }
}

/* ------------------------------------------------------------ movement 3 */

const minutes = (q) => `${String(Math.floor(q / 2)).padStart(2, "0")}:${q % 2 ? "30" : "00"}`;
const brl = (n) => `R$ ${n.toLocaleString("pt-BR")}`;

function tradeSentence(before, after, changed) {
  const d = delta(before, after);
  if (!changed) {
    return `<b>${after.passed}</b> of ${after.total} postings survive. This is the real profile.`;
  }
  if (!d.gained.length && !d.lost.length) {
    return `Still <b>${after.passed}</b> of ${after.total}. That change freed nothing and cost nothing.`;
  }
  const parts = [];
  if (d.gained.length) {
    parts.push(
      `<span class="up"><b>${d.gained.length}</b> more ${d.gained.length === 1 ? "posting" : "postings"} pass</span>`,
    );
  }
  if (d.lost.length) {
    parts.push(
      `<span class="down"><b>${d.lost.length}</b> ${d.lost.length === 1 ? "posting falls" : "postings fall"} out</span>`,
    );
  }
  return `${parts.join(", and ")}. <b>${after.passed}</b> of ${after.total} survive.`;
}

function renderLedger(node, after, before) {
  const d = delta(before, after);
  const moved = new Map();
  for (const x of d.gained) moved.set(x.id + x.title, "gained");
  for (const x of d.lost) moved.set(x.id + x.title, "lost");

  node.innerHTML = after.decisions
    .map((x) => {
      const state = moved.get(x.id + x.title) || "";
      const why =
        x.verdict === "pass"
          ? x.flags.length
            ? "passes, shift unpublished"
            : "passes"
          : x.reasons.map((r) => FILTER_LABELS[r.code] || r.code).join(", ");
      return (
        `<div class="ledger__row"${state ? ` data-moved="${state}"` : ""}>` +
        `<span>${x.title}</span><span class="ledger__why">${why}</span></div>`
      );
    })
    .join("");
}

/* ------------------------------------------------------------ boot */

function observe() {
  const items = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    items.forEach((el) => el.classList.add("is-in"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        }
      }
    },
    { rootMargin: "0px 0px -12% 0px" },
  );
  items.forEach((el) => io.observe(el));
}

async function main() {
  let record;
  let jobs;
  let baseline;
  try {
    [record, jobs, baseline] = await Promise.all([
      loadJSON("data/record.json"),
      loadJSON("data/detailed.json"),
      loadJSON("data/baseline_profile.json"),
    ]);
  } catch (error) {
    const box = document.getElementById("loadError");
    box.hidden = false;
    box.textContent = `${error.message}. The figures below cannot be computed, so none are shown.`;
    return;
  }

  // Movement 1
  const summary = summarizeRecord(record);
  document.getElementById("wallSkipped").textContent = summary.skipped;
  document.getElementById("wallWall").textContent = summary.wall;
  const groups = drawField(document.getElementById("field"), record, summary);
  renderLegend(document.getElementById("legend"), groups, summary.total);
  document.getElementById("fieldNote").textContent =
    `${summary.total} postings. Each mark is one. ${summary.unattributed} of the ${summary.skipped} ` +
    `refusals could not be attributed to a filter and are shown as such.`;

  // Movement 2
  const picker = document.getElementById("picker");
  const nodes = {
    chain: document.getElementById("chain"),
    verdict: document.getElementById("verdict"),
    flagline: document.getElementById("flagline"),
  };
  // Open on a posting that is refused: the machine is more honest, and more
  // interesting, showing why it said no than showing nine clear rows.
  const refused = jobs.filter((j) => screenCorpus([j], baseline).skipped === 1);
  const survives = jobs.filter((j) => screenCorpus([j], baseline).passed === 1);
  const featured = [...refused.slice(0, 4), ...survives.slice(0, 2)];
  picker.innerHTML = featured
    .map(
      (j, i) =>
        `<button type="button" data-index="${i}" aria-pressed="${i === 0}">${j.title}</button>`,
    )
    .join("");
  picker.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    picker.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    renderChain(featured[Number(button.dataset.index)], baseline, nodes);
  });
  renderChain(featured[0], baseline, nodes);

  // Movement 3 and the hero share one state
  const base = screenCorpus(jobs, baseline);
  const state = {
    start: 24,
    end: 44,
    floor: baseline.min_monthly_salary,
    commute: false,
    seniority: baseline.max_seniority,
  };

  const build = () => ({
    ...baseline,
    availability: { start: minutes(state.start), end: minutes(state.end) },
    min_monthly_salary: state.floor,
    onsite_cities: state.commute
      ? [...baseline.onsite_cities, "Sao Paulo", "Curitiba", "Campinas", "Blumenau", "Correia Pinto", "Florianopolis"]
      : baseline.onsite_cities,
    max_seniority: state.seniority,
  });

  const changed = () =>
    state.start !== 24 ||
    state.end !== 44 ||
    state.floor !== baseline.min_monthly_salary ||
    state.commute ||
    state.seniority !== baseline.max_seniority;

  const heroPass = document.getElementById("heroPass");
  const heroTotal = document.getElementById("heroTotal");
  const trade = document.getElementById("trade");
  const ledger = document.getElementById("ledger");
  heroTotal.textContent = base.total;

  function paint() {
    const run = screenCorpus(jobs, build());
    heroPass.textContent = run.passed;
    trade.innerHTML = tradeSentence(base, run, changed());
    renderLedger(ledger, run, base);
    document.getElementById("heroStartValue").textContent = minutes(state.start);
    document.getElementById("ctlStartValue").textContent = minutes(state.start);
    document.getElementById("ctlEndValue").textContent = minutes(state.end);
    document.getElementById("heroFloorValue").textContent = brl(state.floor);
    document.getElementById("ctlFloorValue").textContent = brl(state.floor);
  }

  const bindRange = (id, key, clamp) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = state[key];
    el.addEventListener("input", () => {
      state[key] = Number(el.value);
      if (clamp) clamp();
      const twin = document.getElementById(id.startsWith("hero") ? id.replace("hero", "ctl") : id.replace("ctl", "hero"));
      if (twin) twin.value = state[key];
      paint();
    });
  };

  bindRange("heroStart", "start", () => { if (state.end <= state.start) state.end = state.start + 4; });
  bindRange("ctlStart", "start", () => { if (state.end <= state.start) state.end = state.start + 4; });
  bindRange("ctlEnd", "end", () => { if (state.end <= state.start) state.start = state.end - 4; });
  bindRange("heroFloor", "floor");
  bindRange("ctlFloor", "floor");

  const bindSwitch = (noId, yesId) => {
    const no = document.getElementById(noId);
    const yes = document.getElementById(yesId);
    if (!no || !yes) return;
    const sync = () => {
      for (const pair of [["heroCommuteNo", "heroCommuteYes"], ["ctlCommuteNo", "ctlCommuteYes"]]) {
        const [n, y] = pair.map((x) => document.getElementById(x));
        if (!n) continue;
        n.setAttribute("aria-pressed", String(!state.commute));
        y.setAttribute("aria-pressed", String(state.commute));
      }
      paint();
    };
    no.addEventListener("click", () => { state.commute = false; sync(); });
    yes.addEventListener("click", () => { state.commute = true; sync(); });
  };
  bindSwitch("heroCommuteNo", "heroCommuteYes");
  bindSwitch("ctlCommuteNo", "ctlCommuteYes");

  document.querySelectorAll("[data-seniority]").forEach((button) => {
    button.addEventListener("click", () => {
      state.seniority = button.dataset.seniority;
      document.querySelectorAll("[data-seniority]").forEach((b) =>
        b.setAttribute("aria-pressed", String(b === button)),
      );
      paint();
    });
  });

  document.getElementById("reset").addEventListener("click", () => {
    state.start = 24;
    state.end = 44;
    state.floor = baseline.min_monthly_salary;
    state.commute = false;
    state.seniority = baseline.max_seniority;
    document.getElementById("heroStart").value = 24;
    document.getElementById("ctlStart").value = 24;
    document.getElementById("ctlEnd").value = 44;
    document.getElementById("heroFloor").value = state.floor;
    document.getElementById("ctlFloor").value = state.floor;
    document.querySelectorAll("[data-seniority]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.seniority === state.seniority)),
    );
    for (const pair of [["heroCommuteNo", "heroCommuteYes"], ["ctlCommuteNo", "ctlCommuteYes"]]) {
      const [n, y] = pair.map((x) => document.getElementById(x));
      n.setAttribute("aria-pressed", "true");
      y.setAttribute("aria-pressed", "false");
    }
    paint();
  });

  paint();
  observe();
}

main();
