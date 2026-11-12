from typing import Literal

from app.prompts.qa import FALLBACKS, OFF_TOPIC

ReplyKind = Literal["answer", "fallback", "off_topic"]


def normalize(text: str) -> str:
    return " ".join(text.lower().split()).strip(" \"'`.")


_FALLBACKS = {normalize(reply) for reply in FALLBACKS.values()}
_OFF_TOPIC = {normalize(reply) for reply in OFF_TOPIC.values()}


def reply_kind(answer: str) -> ReplyKind:
    """Classify a model reply: one of the fixed replies, or a real answer."""
    text = normalize(answer)
    if text in _FALLBACKS:
        return "fallback"
    if text in _OFF_TOPIC:
        return "off_topic"
    return "answer"
