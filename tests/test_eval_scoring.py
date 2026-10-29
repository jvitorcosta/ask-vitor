import json
from pathlib import Path

import pytest

from evals.scoring import (
    Case,
    is_fallback,
    markdown_table,
    score,
    summarize,
    unsupported_numbers,
)

FALLBACK = "I don't have information about that."
CONTEXT = ["The model cut alerts by 99.2% over 24 months.", "He works in Python."]
QUESTIONS = Path(__file__).resolve().parents[1] / "evals" / "questions.json"


def in_scope(*groups: tuple[str, ...]) -> Case:
    return Case(id="q", kind="in_scope", question="?", expect=groups)


def refuse_case() -> Case:
    return Case(id="q", kind="out_of_scope", question="?")


@pytest.mark.parametrize(
    "answer",
    [FALLBACK, "i don't have information about that", '"I don\'t have information about that."'],
)
def test_is_fallback_tolerates_case_quotes_and_punctuation(answer: str) -> None:
    assert is_fallback(answer, FALLBACK)


def test_unsupported_numbers_flags_only_numbers_missing_from_context() -> None:
    assert unsupported_numbers("Alerts fell 99.2% in 2023, over 24 months.", CONTEXT) == ("2023",)


def test_unsupported_numbers_treats_decimal_comma_as_dot() -> None:
    assert unsupported_numbers("Alerts fell 99,2%.", CONTEXT) == ()


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        ("It cut alerts by 99.2%.", "correct"),
        (FALLBACK, "missed"),
        ("It cut alerts by 95%.", "invented"),
        ("It cut alerts a lot.", "wrong"),
    ],
)
def test_score_in_scope(answer: str, verdict: str) -> None:
    result = score(in_scope(("99.2",)), answer, 1.0, context=CONTEXT, fallback=FALLBACK)
    assert result.verdict == verdict
    assert result.passed is (verdict == "correct")


def test_score_requires_every_expected_group() -> None:
    case = in_scope(("python",), ("spark", "databricks"))
    result = score(case, "He uses Python.", 1.0, context=CONTEXT, fallback=FALLBACK)
    assert result.verdict == "wrong"


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        (FALLBACK, "refused"),
        ("I don't have information about Vitor's age.", "declined"),
        ("His salary is not specified in the context.", "declined"),
        ("Vitor is 36 years old.", "answered"),
        ("Paris.", "answered"),
    ],
)
def test_score_questions_that_must_be_refused(answer: str, verdict: str) -> None:
    result = score(refuse_case(), answer, 1.0, context=CONTEXT, fallback=FALLBACK)
    assert result.verdict == verdict
    assert result.passed is (verdict == "refused")
    assert result.safe_refusal is (verdict in ("refused", "declined"))


def test_a_decline_with_an_invented_number_is_not_safe() -> None:
    answer = "There is no information, but probably around 2019."
    assert score(refuse_case(), answer, 1.0, context=CONTEXT, fallback=FALLBACK).verdict == (
        "answered"
    )


def test_a_decline_on_an_in_scope_question_is_a_miss() -> None:
    answer = "That is not mentioned."
    result = score(in_scope(("python",)), answer, 1.0, context=CONTEXT, fallback=FALLBACK)
    assert result.verdict == "missed"


def test_summarize_splits_answer_and_refusal_accuracy() -> None:
    results = [
        score(in_scope(("python",)), "Python.", 1.0, context=CONTEXT, fallback=FALLBACK),
        score(in_scope(("python",)), FALLBACK, 2.0, context=CONTEXT, fallback=FALLBACK),
        score(refuse_case(), FALLBACK, 3.0, context=CONTEXT, fallback=FALLBACK),
        score(refuse_case(), "That is not mentioned.", 4.0, context=CONTEXT, fallback=FALLBACK),
        score(refuse_case(), "In 1990.", 5.0, context=CONTEXT, fallback=FALLBACK),
    ]

    summary = summarize("m", results)

    assert summary.answer_accuracy == 0.5
    assert summary.refusal_accuracy == pytest.approx(1 / 3)
    assert summary.safe_refusal_rate == pytest.approx(2 / 3)
    assert summary.invented_rate == 0.2
    assert summary.latency_p50_s == 3.0
    assert summary.latency_p95_s == 5.0
    assert (summary.passed, summary.total) == (2, 5)
    assert "| `m` | 2/5 | 50% | 33% | 67% | 20% | 3.00s | 5.00s |" in markdown_table([summary])


def test_question_set_is_well_formed() -> None:
    cases = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]

    assert len(ids) == len(set(ids))
    assert {case["kind"] for case in cases} == {
        "in_scope",
        "out_of_scope",
        "false_premise",
        "injection",
    }
    assert all(case.get("expect") for case in cases if case["kind"] == "in_scope")
