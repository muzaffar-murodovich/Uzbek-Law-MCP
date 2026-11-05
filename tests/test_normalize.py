import pytest

from qonunshunos.text.normalize import (
    clean_whitespace,
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
