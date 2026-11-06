import pytest

from pipeline.truth_gate import Rules, normalize, validate

RULES = "config/truth_rules.example.json"
MASTER = "examples/cv_master.txt"
PASSING = "examples/cv_sample_pass.txt"
FAILING = "examples/cv_sample_fail.txt"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def rules():
    return Rules.load(RULES)


@pytest.fixture(scope="module")
def master():
    return read(MASTER)


def failed_names(result):
    return {c.name for c in result.failed}


def test_tailored_variant_is_approved(rules, master):
    result = validate(read(PASSING), master, rules)
    assert result.approved, result.render()


def test_inflated_variant_is_rejected(rules, master):
    result = validate(read(FAILING), master, rules)
    assert not result.approved
    assert "3. no unsupported claims" in failed_names(result)
    assert "2. contained in master" in failed_names(result)


def test_a_line_absent_from_the_master_is_an_orphan(rules, master):
    cv = read(PASSING) + "\n- Led a team of six engineers.\n"
    result = validate(cv, master, rules)
    assert "2. contained in master" in failed_names(result)


def test_invented_metric_is_caught(rules, master):
    cv = read(PASSING).replace(
        "- Maintains a public GitHub profile with study projects.",
        "- Improved response time by 40%.",
    )
    assert "3. no unsupported claims" in failed_names(validate(cv, master, rules))


def test_unconfirmed_skill_is_caught(rules, master):
    cv = read(PASSING).replace(
        "Languages: Python, JavaScript, Java, HTML, CSS, SQL",
        "Languages: Python, JavaScript, Kubernetes, SQL",
    )
    assert "5. only confirmed skills" in failed_names(validate(cv, master, rules))


def test_emoji_breaks_the_ats_gate(rules, master):
    cv = read(PASSING).replace("PROJECTS", "PROJECTS ✓")
    assert "B. no icons or emoji" in failed_names(validate(cv, master, rules))


def test_overlong_cv_is_rejected(rules, master):
    cv = read(PASSING) + ("\nfiller " * 600)
    assert "F. fits one page" in failed_names(validate(cv, master, rules))


def test_gate_never_edits_its_input(rules, master):
    original = read(FAILING)
    validate(original, master, rules)
    assert read(FAILING) == original


def test_normalize_folds_accents_and_markers():
    assert normalize("  - Integração de Serviços.") == "integracao de servicos"
