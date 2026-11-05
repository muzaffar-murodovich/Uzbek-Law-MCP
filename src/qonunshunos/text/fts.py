"""Full-text search normalization for Uzbek Latin.

PostgreSQL has no Uzbek stemmer, so text is normalized here and handed to the ``simple``
configuration as space-separated terms. Queries go through the very same function.
"""

import re

from qonunshunos.text.normalize import fold

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
                word = word[: -len(suffix)]
                break
        if word in _KEEP:
            return word
    if word.endswith("lig"):
        word = word[:-1] + "k"  # majburiyligi → majburiylig → majburiylik
    return word


def terms(text: str, use_stem: bool = True) -> list[str]:
    """Folded, apostrophe-free terms without stopwords (optionally stemmed)."""
    words = _WORD_RE.findall(fold(text).translate(_DROP))
    out = []
    for word in words:
        if word in STOPWORDS:
            continue
        out.append(stem(word) if use_stem and not word.isdigit() else word)
    return out


def to_fts_text(text: str, use_stem: bool = True) -> str:
    return " ".join(terms(text, use_stem))


def to_tsquery(text: str, use_stem: bool = True) -> str | None:
    """OR query for ``to_tsquery('simple', ...)``; ``None`` if nothing is left."""
    unique = list(dict.fromkeys(terms(text, use_stem)))
    return " | ".join(unique) if unique else None
