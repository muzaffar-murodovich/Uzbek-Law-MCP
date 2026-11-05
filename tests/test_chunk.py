from qonunshunos.parser.models import Paragraph, Table, Unit
from qonunshunos.text.chunk import PIECE_TARGET, SINGLE_MAX, chunk_unit, heading_for


def _unit(*texts: str, **kw) -> Unit:
    return Unit(
        kind=kw.pop("kind", "modda"),
        paragraphs=[Paragraph(elem_id=i, text=t) for i, t in enumerate(texts)],
        **kw,
    )


def test_heading_has_document_last_path_levels_and_label():
    unit = _unit(
        "x", number="161", title="Bekor qilish", path=["MAXSUS QISM", "IV BOʻLIM", "12-bob"]
    )
    assert (
        heading_for("Mehnat kodeksi", unit)
        == "Mehnat kodeksi. IV BOʻLIM. 12-bob. 161-modda. Bekor qilish"
    )


def test_short_unit_is_one_chunk():
    chunks = chunk_unit("K", _unit("Birinchi.", "Ikkinchi.", number="1"))
    assert [c.text for c in chunks] == ["Birinchi.\nIkkinchi."]
    assert chunks[0].passage.startswith("K. 1-modda\n")


def test_long_unit_repeats_lead_paragraph():
    items = [f"{i}) " + " ".join(["soʻz"] * 60) for i in range(1, 12)]
    chunks = chunk_unit("K", _unit("Quyidagilar taqiqlanadi:", *items, number="5"))
    assert len(chunks) > 1
    assert all(c.text.startswith("Quyidagilar taqiqlanadi:\n") for c in chunks)
    assert all(len(c.text) <= PIECE_TARGET + 50 for c in chunks)
    body = "\n".join(c.text.removeprefix("Quyidagilar taqiqlanadi:\n") for c in chunks)
    assert body.split("\n") == items


def test_overlong_paragraph_is_cut_at_sentences():
    text = " ".join(f"Gap {i} " + "soʻz " * 30 + "." for i in range(20))
    chunks = chunk_unit("K", _unit(text))
    assert len(text) > SINGLE_MAX and len(chunks) > 1
    assert all(len(c.text) <= PIECE_TARGET for c in chunks)


def test_tables_and_empty_units():
    unit = _unit(number="2", tables=[Table(elem_id=1, rows=[["A", "B"], ["1", ""]])])
    assert chunk_unit("K", unit)[0].text == "A | B\n1"
    assert chunk_unit("K", _unit(number="3", title="Chiqarib tashlangan"))[0].text == (
        "Chiqarib tashlangan"
    )
    assert chunk_unit("K", _unit(number="4")) == []
