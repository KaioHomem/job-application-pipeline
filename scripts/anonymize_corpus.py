#!/usr/bin/env python3
"""Turn the private tracker into a record that can be published.

This produces the **aggregate record only** — counts, reason codes and dates.
It cannot produce a re-screenable corpus, and does not try: the tracker stores
`date, company, role, source, url, status, next_action, proof, notes` and has
no `work_model`, `schedule`, `required_tech` or `seniority`. The facts a note
preserves are only the ones the firing filter happened to interpolate, so a row
reading "[location] Onsite in Curitiba; outside the commutable area." records
nothing about that posting's shift or stack.

Inventing those fields to make the page interactive is exactly what the truth
gate exists to prevent. The postings that can be re-screened are hand-labelled
in web/data/detailed.json instead.

    python scripts/anonymize_corpus.py --tracker <path> --out web/data/record.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re

CODE = re.compile(r"\[([a-z?]+)\]")

# Rows written before the tracker carried bracketed codes hold the reason as
# Portuguese prose. Those are classified here by keyword, in filter order, so
# the bucket matches the first filter that would have fired. A classified code
# is marked `code_source: "classified"` and never passed off as one the engine
# emitted — the page labels the two differently.
CLASSIFIERS = [
    ("closed", r"expir|encerrad|fechou|\bclosed\b|nao esta mais"),
    ("affirmative", r"afirmativa|exclusiva para (pessoas|mulheres|negr)"),
    ("location", r"presenc|h[ií]brid|fora de lages|outside|mudan[cç]a|residir|relocat|"
                 r"remoto de|outro estado|anywhere in"),
    ("schedule", r"hor[aá]ri|jornada|turno|manh[aã]|expediente|\d{1,2}[:h]\d{2}|"
                 r"colide com as aulas"),
    ("seniority", r"\bs[eê]nior\b|\bpleno\b|especialista|\blead\b|coordenador|gerente"),
    ("degree", r"superior completo|j[aá] formado|diploma"),
    ("field", r"curso n[aã]o|exige .*(administra|cont[aá]be|psicologia|turismo|letras)|"
              r"[aá]rea n[aã]o"),
    ("tech", r"sem lastro|n[aã]o (tem|possui) .*(experi|conhecimento)|react|\.net|vue|"
             r"angular|fibra [oó]ptica|cftv|testlink|graphql|pyspark|mlops|linux|"
             r"active directory|intune|\bcnh\b"),
    ("experience", r"\d+\+? ?anos? de experi|experi[eê]ncia (profissional|comprovada)|"
                   r"\d+\+ ano"),
    ("salary", r"sal[aá]rio|remunera[cç][aã]o|abaixo do piso|bolsa abaixo"),
]


def classify_note(notes: str) -> str | None:
    """Derive the first filter that would have fired, from a prose note."""
    folded = notes.casefold()
    for code, pattern in CLASSIFIERS:
        if re.search(pattern, folded):
            return code
    return None

ROLE_FAMILIES = [
    ("estagio", r"est[aá]gi|estagi|trainee|aprendiz|intern"),
    ("suporte", r"suporte|service ?desk|help ?desk|atendimento|support"),
    ("dados", r"dados|data|bi\b|anal[ií]tic|business intelligence"),
    ("qa", r"\bqa\b|qualidade|teste|quality"),
    ("dev", r"desenvolv|develop|程|software|backend|front[- ]?end|full ?stack|program"),
]


def role_family(title: str) -> str:
    folded = title.casefold()
    for name, pattern in ROLE_FAMILIES:
        if re.search(pattern, folded):
            return name
    return "outro"


def _company_ids(rows: list[dict]) -> dict[str, str]:
    """Stable, sorted numbering so a regeneration produces the same ids."""
    names = sorted({(r.get("Company") or "").strip() for r in rows})
    return {name: f"Empresa #{i:03d}" for i, name in enumerate(names, start=1)}


def anonymize(rows: list[dict]) -> list[dict]:
    ids = _company_ids(rows)
    out: list[dict] = []
    for row in rows:
        notes = row.get("Notes") or ""
        status = (row.get("Status") or "").strip().casefold().replace(" ", "_")
        codes = CODE.findall(notes)
        if codes:
            primary, source = codes[0], "recorded"
        elif status == "skipped":
            primary = classify_note(notes)
            source = "classified" if primary else None
        else:
            primary, source = None, None
        out.append(
            {
                "id": ids[(row.get("Company") or "").strip()],
                "role_family": role_family(row.get("Role") or ""),
                "source": (row.get("Source") or "unknown").strip(),
                "date": (row.get("Date") or "").strip(),
                "status": status,
                "codes": codes,
                # Movement 1 counts this one, so each posting lands in exactly
                # one bucket and the buckets sum to the number skipped. The
                # engine itself does not short-circuit; this is the first of
                # possibly several, and the page says so.
                "primary_code": primary,
                # "recorded" = the engine wrote the code. "classified" = derived
                # from a prose note by the keyword rules above. The page must
                # not present the second as if it were the first.
                "code_source": source,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", required=True, help="path to the private tracker CSV")
    parser.add_argument("--out", default=os.path.join("web", "data", "record.json"))
    args = parser.parse_args()

    with open(args.tracker, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    records = anonymize(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(records, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
