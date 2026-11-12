from app.knowledge.facts import Fact
from app.prompts.qa import FALLBACK_ANSWER, FALLBACKS, OFF_TOPIC, build_messages

FACTS = [
    Fact("cv.nubank", "CV · Experience", "2026-11-12", "Vitor worked at Nubank."),
    Fact("cv.edu", "CV · Education", "2026-11-12", "Vitor studied computer science."),
]


def test_system_message_holds_rules_and_context() -> None:
    system = build_messages(FACTS, "Where did he work?")[0]

    assert system["role"] == "system"
    for fact in FACTS:
        assert f"[{fact.id}] {fact.text}" in system["content"]
    for reply in (*FALLBACKS.values(), *OFF_TOPIC.values()):
        assert reply in system["content"]
    assert "<<sources:" in system["content"]


def test_user_message_is_only_the_question() -> None:
    messages = build_messages(FACTS, "Where did he work?")

    assert messages[1] == {"role": "user", "content": "Where did he work?"}


def test_system_prompt_lists_never_share_topics() -> None:
    content = build_messages(FACTS, "x")[0]["content"].lower()

    for topic in ("salary", "address", "health", "family"):
        assert topic in content


def test_fallback_answer_stays_english_fallback() -> None:
    assert FALLBACK_ANSWER == FALLBACKS["en"] == "I don't have information about that."
