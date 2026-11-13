"""Hide the model's final ``<<sources: id1, id2>>`` line from a token stream."""

import re

MARKER = "<<sources:"
_ID = re.compile(r"[a-z0-9._-]+")


def _partial_marker_len(text: str) -> int:
    """Length of the longest suffix of text that is a proper prefix of MARKER."""
    for size in range(min(len(MARKER) - 1, len(text)), 0, -1):
        if text.endswith(MARKER[:size]):
            return size
    return 0


class SourcesTrailer:
    def __init__(self) -> None:
        self._held = ""
        self._trailer = ""
        self._in_trailer = False

    def feed(self, token: str) -> str:
        """Return the part of the stream that is safe to show now."""
        if self._in_trailer:
            self._trailer += token
            return ""
        text = self._held + token
        index = text.find(MARKER)
        if index >= 0:
            self._in_trailer = True
            self._trailer = text[index + len(MARKER) :]
            self._held = ""
            return text[:index].rstrip()
        head = text[: len(text) - _partial_marker_len(text)].rstrip()
        self._held = text[len(head) :]
        return head

    def finish(self) -> tuple[str, list[str]]:
        """Return the remaining visible text and the cited ids, in order, deduplicated."""
        if self._in_trailer:
            visible = ""
        else:
            visible = self._held.rstrip()
        self._held = ""
        ids: list[str] = []
        body = self._trailer.split(">>", 1)[0]
        for part in body.split(","):
            candidate = part.strip()
            if _ID.fullmatch(candidate) and candidate not in ids:
                ids.append(candidate)
        return visible, ids
