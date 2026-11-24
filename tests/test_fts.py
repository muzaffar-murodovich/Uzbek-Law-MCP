import pytest

from nizom.text.fts import stem, terms, to_tsquery


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


@pytest.mark.parametrize(
    "forms",
    [
        ["beruvchi", "beruvchiga", "beruvchilar", "beruvchisi", "beruvchimizga"],
        ["shahar", "shaharda", "shahri", "shahrida", "shahrimizda"],
        ["kodeks", "kodeksi", "kodeksining"],
        ["soliq", "solig‘i", "soliqlar", "soliqqa"],
        ["o‘g‘il", "o‘g‘li", "o‘g‘illari"],
    ],
)
def test_forms_of_one_word_share_a_term(forms):
    assert len({" ".join(terms(f)) for f in forms}) == 1


@pytest.mark.parametrize(
    ("derived", "base"),
    [("ishsiz", "ish"), ("raqamli", "raqam"), ("taqiqlanmagan", "taqiqlangan"), ("birov", "bir")],
)
def test_meaning_changing_suffixes_stay(derived, base):
    assert terms(derived) != terms(base)
