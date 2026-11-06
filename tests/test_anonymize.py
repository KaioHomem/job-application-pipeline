import json

from scripts.anonymize_corpus import anonymize, role_family


def row(**kw):
    base = {
        "Date": "2026-09-08",
        "Company": "Instituto Exemplo",
        "Role": "Estagio em Desenvolvimento Web",
        "Source": "gupy",
        "URL": "https://example.com/1",
        "Status": "Skipped",
        "Next Action": "",
        "Notes": "[location] Onsite in Campinas; outside the commutable area.",
    }
    base.update(kw)
    return base


def test_company_names_never_survive():
    out = anonymize([row(Company="Instituto Eldorado")])
    assert "Eldorado" not in json.dumps(out, ensure_ascii=False)
    assert out[0]["id"].startswith("Empresa #")


def test_the_same_company_gets_the_same_id():
    out = anonymize([row(Company="ACME"), row(Company="ACME", URL="https://example.com/2")])
    assert out[0]["id"] == out[1]["id"]


def test_different_companies_get_different_ids():
    out = anonymize([row(Company="ACME"), row(Company="Globex")])
    assert out[0]["id"] != out[1]["id"]


def test_numbering_is_stable_across_runs():
    rows = [row(Company="Zeta"), row(Company="Alpha"), row(Company="Mu")]
    assert [r["id"] for r in anonymize(rows)] == [r["id"] for r in anonymize(rows)]


def test_reason_codes_are_extracted_from_notes():
    out = anonymize([row(Notes="[schedule] Shift 09:00-16:00 falls outside the window.")])
    assert out[0]["codes"] == ["schedule"]
    assert out[0]["primary_code"] == "schedule"


def test_the_first_code_is_the_primary_one():
    out = anonymize([row(Notes="[location] Onsite. [schedule] Morning.")])
    assert out[0]["codes"] == ["location", "schedule"]
    assert out[0]["primary_code"] == "location"


def test_a_row_without_codes_has_no_primary_code():
    out = anonymize([row(Status="Applied", Notes="Sent 2026-09-21, confirmation archived.")])
    assert out[0]["primary_code"] is None


def test_status_is_normalized():
    assert anonymize([row(Status="Needs Human Action")])[0]["status"] == "needs_human_action"


def test_no_url_or_next_action_is_published():
    published = set(anonymize([row()])[0].keys())
    assert "url" not in published
    assert "next_action" not in published


def test_role_family_is_classified():
    assert role_family("Analista de Suporte Junior") == "suporte"
    assert role_family("Estagio em Desenvolvimento de Software") == "estagio"
    assert role_family("Analista de Dados Junior") == "dados"
    assert role_family("Analista de Testes Junior") == "qa"
    assert role_family("Desenvolvedor Backend Junior") == "dev"
    assert role_family("Auxiliar de Expedicao") == "outro"


def test_a_prose_note_is_classified_and_marked_as_such():
    out = anonymize([row(Notes="Presencial em Curitiba, fora da regiao.")])
    assert out[0]["primary_code"] == "location"
    assert out[0]["code_source"] == "classified"


def test_a_bracketed_note_is_marked_as_recorded():
    out = anonymize([row(Notes="[schedule] Shift 09:00-16:00 falls outside.")])
    assert out[0]["code_source"] == "recorded"


def test_classification_follows_filter_order():
    # Mentions both location and schedule; location comes first in the chain.
    out = anonymize([row(Notes="Presencial em Joinville, horario 08:00 as 17:00.")])
    assert out[0]["primary_code"] == "location"


def test_only_skipped_rows_are_classified():
    out = anonymize([row(Status="Applied", Notes="Presencial em Curitiba.")])
    assert out[0]["primary_code"] is None
    assert out[0]["code_source"] is None


def test_an_unclassifiable_skip_stays_honest():
    out = anonymize([row(Notes="Pulada.")])
    assert out[0]["primary_code"] is None
    assert out[0]["code_source"] is None
