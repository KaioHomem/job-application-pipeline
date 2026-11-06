import json

from scripts.gen_parity_expected import CORPUS, EXPECTED, build_expected

ALL_CODES = {
    "closed",
    "affirmative",
    "location",
    "schedule",
    "seniority",
    "degree",
    "field",
    "tech",
    "experience",
    "salary",
}


def corpus():
    with open(CORPUS, encoding="utf-8") as fh:
        return json.load(fh)


def committed():
    with open(EXPECTED, encoding="utf-8") as fh:
        return json.load(fh)


def test_committed_expectations_match_the_python_filters():
    assert build_expected(corpus()) == committed()


def test_corpus_exercises_every_reason_code():
    seen = {code for row in build_expected(corpus()) for code in row["codes"]}
    assert seen == ALL_CODES


def test_corpus_exercises_the_schedule_flag():
    assert any("schedule?" in row["flags"] for row in build_expected(corpus()))


def test_some_postings_survive_every_filter():
    assert any(row["verdict"] == "pass" for row in build_expected(corpus()))


def test_messages_travel_with_codes():
    for row in build_expected(corpus()):
        assert len(row["messages"]) == len(row["codes"])
        for message in row["messages"]:
            assert message.endswith(".")
