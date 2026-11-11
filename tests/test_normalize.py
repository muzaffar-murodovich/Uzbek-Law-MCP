import pytest

from qonunshunos.text.normalize import (
    APOSTROPHES,
    clean_whitespace,
    embedding_text,
    fold,
    normalize_apostrophes,
    normalize_text,
    to_superscript,
)


@pytest.mark.parametrize("variant", ["'", "`", "‘", "’", "ʻ", "ʼ"])
def test_okina_after_o_and_g(variant):
    assert normalize_apostrophes(f"to{variant}g{variant}risida") == "toʻgʻrisida"
    assert normalize_apostrophes(f"O{variant}RQ-42") == "OʻRQ-42"


@pytest.mark.parametrize("variant", ["'", "`", "‘", "’", "ʻ"])
def test_tutuq_after_other_letters(variant):
    assert normalize_apostrophes(f"ma{variant}lumot") == "maʼlumot"
    assert normalize_apostrophes(f"ta{variant}lim") == "taʼlim"


def test_quotes_at_word_boundaries_are_kept():
    assert normalize_apostrophes("'Adolat' markazi") == "'Adolat' markazi"
    assert normalize_apostrophes("‘test’") == "‘test’"


def test_clean_whitespace_handles_nbsp_and_newlines():
    assert clean_whitespace("  1-modda.\n\t Asosiy  qoidalar ") == "1-modda. Asosiy qoidalar"


def test_to_superscript():
    assert to_superscript("126") == "¹²⁶"


def test_normalize_text_and_fold():
    assert normalize_text("  Mehnat  kodeksi, o'zgartirish ") == "Mehnat kodeksi, oʻzgartirish"
    assert fold("O‘ZBEKISTON Respublikasi") == "oʻzbekiston respublikasi"


def test_apostrophe_code_points():
    # Several of these look identical, so the set is pinned by code point.
    assert sorted(ord(c) for c in APOSTROPHES) == sorted(
        [0x0027, 0x0060, 0x2018, 0x2019, 0x02BB, 0x02BC, 0x00B4, 0x02B9]
    )


@pytest.mark.parametrize("variant", ["\u0027", "\u0060", "\u2019", "\u02bb", "\u00b4"])
def test_embedding_text_uses_quotation_marks(variant):
    text = embedding_text(f"to{variant}g{variant}risida ma{variant}lumot")
    assert text == "to\u2018g\u2018risida ma\u2019lumot"
