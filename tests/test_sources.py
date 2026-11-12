from app.services.sources import SourcesTrailer

FULL = "He worked at Nubank.\n<<sources: cv.nubank, cv.skills>>"


def run(tokens: list[str]) -> tuple[str, list[str]]:
    trailer = SourcesTrailer()
    shown = "".join(trailer.feed(t) for t in tokens)
    rest, ids = trailer.finish()
    return shown + rest, ids


def test_passes_plain_text_through():
    assert run(["He ", "worked."]) == ("He worked.", [])


def test_strips_trailer_split_anywhere():
    for i in range(len(FULL) + 1):
        assert run([FULL[:i], FULL[i:]]) == ("He worked at Nubank.", ["cv.nubank", "cv.skills"])


def test_strips_trailer_fed_char_by_char():
    assert run(list(FULL)) == ("He worked at Nubank.", ["cv.nubank", "cv.skills"])


def test_lone_angle_bracket_is_released():
    trailer = SourcesTrailer()
    shown = trailer.feed("a <") + trailer.feed(" b")
    rest, ids = trailer.finish()
    assert shown + rest == "a < b"
    assert ids == []


def test_unclosed_trailer_is_hidden():
    assert run(["Hi.<<sources: cv"]) == ("Hi.", ["cv"])


def test_duplicate_ids_are_dropped():
    assert run(["Ok.\n<<sources: a, b, a>>"]) == ("Ok.", ["a", "b"])
