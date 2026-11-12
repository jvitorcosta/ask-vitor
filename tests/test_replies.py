from app.services.replies import normalize, reply_kind


def test_reply_kind() -> None:
    assert reply_kind("Não tenho informação sobre isso.") == "fallback"
    assert reply_kind(" I only answer questions about Vitor. ") == "off_topic"
    assert reply_kind("He worked at Nubank.") == "answer"


def test_normalize_strips_quotes_dots_and_spaces() -> None:
    assert normalize('  "Hello   World." ') == "hello world"
