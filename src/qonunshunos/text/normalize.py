"""Text normalization for Uzbek Latin legal texts.

Official lex.uz texts use U+02BB (``oʻ``, ``gʻ``) and U+02BC (tutuq belgisi, ``maʼlumot``),
while users type ``o'``, ``o‘``, ``o’`` or ``o```. Everything is brought to the official form.
"""

import re

OKINA = "ʻ"  # ʻ  — after o / g
TUTUQ = "ʼ"  # ʼ  — after any other letter

# All characters people use in place of ʻ and ʼ.
APOSTROPHES = "'`‘’ʻʼ´ʹ"

_APOSTROPHE_RE = re.compile(rf"(?<=([^\W\d_]))[{re.escape(APOSTROPHES)}](?=[^\W\d_])")
_WHITESPACE_RE = re.compile(r"\s+")

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _apostrophe(match: re.Match[str]) -> str:
    return OKINA if match.group(1) in "oOgG" else TUTUQ


def normalize_apostrophes(text: str) -> str:
    """Replace apostrophe look-alikes between two letters with ʻ (after o/g) or ʼ.

    Quotes at word boundaries (``'Adolat'``) are left untouched.
    """
    return _APOSTROPHE_RE.sub(_apostrophe, text)


def clean_whitespace(text: str) -> str:
    """Collapse all whitespace (including NBSP) to single spaces and strip."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def to_superscript(digits: str) -> str:
    """``"12"`` → ``"¹²"`` (used for inserted articles and items: ``126¹``)."""
    return digits.translate(_SUPERSCRIPT)


def normalize_text(text: str) -> str:
    """Canonical form for storing parsed text."""
    return normalize_apostrophes(clean_whitespace(text))


def fold(text: str) -> str:
    """Canonical lower-case form for matching user queries against stored text."""
    return normalize_text(text).lower()
