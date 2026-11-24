"""Full-text search normalization for Uzbek Latin.

PostgreSQL has no Uzbek stemmer, so text is normalized here and handed to the ``simple``
configuration as space-separated terms. Queries go through the very same function.
"""

import gzip
import re
from functools import cache
from importlib import resources

from nizom.text.normalize import fold

_DROP = str.maketrans({"ʻ": None, "ʼ": None, "⁰": "0", "¹": "1", "²": "2", "³": "3",
                       "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"})  # fmt: skip
_WORD_RE = re.compile(r"[^\W_]+")

STOPWORDS = frozenset(
    """va yoki bilan uchun boʻyicha hamda ham esa lekin ammo biroq agar ning bu shu u ular
    oʻz har bir qaysi qanday nima nega qachon kim qayerda qancha mi emas edi ekan etib
    deb kabi koʻra qadar sababli tomonidan orqali toʻgʻrisida haqida mumkin mumkinmi
    menga meni men biz siz""".replace("ʻ", "")
    .replace("ʼ", "")
    .split()
)

# Light stemmer: at most one suffix per morphological slot, stripped right to left
# (case → possessive → plural). First and second person possessives (-im, -ing) and the
# question particle -mi are not stripped: too many stems end with them (xodim, tizim, qism).
# Consistency between documents and queries matters more than linguistic accuracy.
# Derivational suffixes are kept.
_SLOTS: list[list[tuple[str, int]]] = [  # (suffix, minimal stem length)
    [("gacha", 3), ("dagi", 3), ("ning", 3), ("dan", 3), ("ni", 3), ("ga", 3), ("da", 4)],
    [("imiz", 3), ("ingiz", 3), ("lari", 3), ("si", 3), ("i", 3)],
    [("lar", 3)],
]
_KEEP = frozenset({"modda", "ham", "bola", "boshqa", "yana"})


def stem(word: str) -> str:
    if word in _KEEP:
        return word
    for slot in _SLOTS:
        for suffix, min_len in slot:
            if word.endswith(suffix) and len(word) - len(suffix) >= min_len:
                if suffix[0] == "i" and word[: -len(suffix)].endswith("ch"):
                    suffix = suffix[1:]  # keep the i of agent nouns: beruvchi(miz), not -imiz
                if suffix:
                    word = word[: -len(suffix)]
                break
        if word in _KEEP:
            return word
    if word.endswith("lig"):
        word = word[:-1] + "k"  # majburiyligi → majburiylig → majburiylik
    return word


# Stems whose vowel drops before a suffix (shahar → shahri): the suffix stripper and the
# lemma table both leave the short form, so it is mapped to the full one.
_ELISION = {
    "shahr": "shahar", "ogl": "ogil", "burn": "burun", "qorn": "qorin", "kongl": "kongil",
    "bogz": "bogiz", "ogz": "ogiz", "bagr": "bagir", "singl": "singil", "zehn": "zehin",
}  # fmt: skip


@cache
def _lemmas() -> dict[str, str]:
    """Word → lemma, FTS form, from the uzmorph analyser (scripts/build_lemmas.py).

    Only the words whose stem changes through the lemma are listed (52k of 229k corpus words):
    beruvchiga → beruvchi, kodeksi → kodeks, soliqqa → soliq.
    """
    raw = resources.files("nizom.text").joinpath("lemmas.tsv.gz").read_bytes()
    lines = gzip.decompress(raw).decode("utf-8").splitlines()
    return dict(line.split("\t", 1) for line in lines)


def term(word: str) -> str:
    """FTS term of one folded, apostrophe-free word: stem of its lemma when the corpus has it.

    Stemming the lemma (not using it as is) keeps a known form and an unseen form of the same
    word together: beruvchiga → beruvchi → beruvch, and beruvchimizga → beruvch.
    """
    stemmed = stem(_lemmas().get(word, word))
    return _ELISION.get(stemmed, stemmed)


def terms(text: str, use_stem: bool = True) -> list[str]:
    """Folded, apostrophe-free terms without stopwords (optionally lemmatised and stemmed)."""
    words = _WORD_RE.findall(fold(text).translate(_DROP))
    out = []
    for word in words:
        if word in STOPWORDS:
            continue
        out.append(term(word) if use_stem and not word.isdigit() else word)
    return out


def to_fts_text(text: str, use_stem: bool = True) -> str:
    return " ".join(terms(text, use_stem))


def to_tsquery(text: str, use_stem: bool = True) -> str | None:
    """OR query for ``to_tsquery('simple', ...)``; ``None`` if nothing is left."""
    unique = list(dict.fromkeys(terms(text, use_stem)))
    return " | ".join(unique) if unique else None
