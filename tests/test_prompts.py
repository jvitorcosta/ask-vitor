from app.knowledge.data import KNOWLEDGE_BASE
from app.prompts.qa import FALLBACK_ANSWER, SYSTEM_PROMPT, build_messages


def test_build_messages_includes_system_prompt_and_all_context() -> None:
    system, user = build_messages(KNOWLEDGE_BASE, "Who is the CEO?")

    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    for snippet in KNOWLEDGE_BASE:
        assert snippet in user["content"]


def test_build_messages_wraps_question_in_delimiters() -> None:
    _, user = build_messages(["Some fact."], "Who is the CEO?")

    assert "<question>\nWho is the CEO?\n</question>" in user["content"]
    assert user["content"].index("</context>") < user["content"].index("<question>")


def test_system_prompt_defines_fallback() -> None:
    assert FALLBACK_ANSWER in SYSTEM_PROMPT
