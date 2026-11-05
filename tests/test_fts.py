import pytest

from qonunshunos.text.fts import stem, terms, to_tsquery


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("xodimlarning", "xodim"),
        ("xodimi", "xodim"),
        ("xodim", "xodim"),
        ("moddasining", "modda"),
        ("moddada", "modda"),
        ("modda", "modda"),
        ("qoidalariga", "qoida"),
        ("imtiyozlari", "imtiyoz"),
        ("bolalarni", "bola"),
        ("majburiyligi", "majburiylik"),
        ("ish", "ish"),
        ("ishdan", "ish"),
    ],
)
def test_stem(word, expected):
    assert stem(word) == expected


def test_terms_fold_apostrophes_and_drop_stopwords():
    # every apostrophe variant gives the same term, stopwords disappear
    assert terms("koʻra boʻshatish") == terms("ko'ra bo‘shatish") == ["boshatish"]
    assert terms("ta'til va mehnat") == ["tatil", "mehnat"]


def test_terms_superscripts_become_digits():
    assert terms("126¹-modda", use_stem=False) == ["1261", "modda"]


def test_to_tsquery_is_or_of_unique_terms():
    assert to_tsquery("ishdan bo'shatish ishdan") == "ish | boshatish"
    assert to_tsquery("va yoki") is None
