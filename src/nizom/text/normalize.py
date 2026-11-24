"""Text normalization for Uzbek Latin legal texts.

Official lex.uz texts use U+02BB (``oʻ``, ``gʻ``) and U+02BC (tutuq belgisi, ``maʼlumot``),
while users type ``o'``, ``o‘``, ``o’`` or ``o```. Everything is brought to the official form.
"""

import re

OKINA = "\u02bb"  # MODIFIER LETTER TURNED COMMA: oʻ, gʻ (official lex.uz form)
TUTUQ = "\u02bc"  # MODIFIER LETTER APOSTROPHE: tutuq belgisi (official lex.uz form)

# All characters people use in place of ʻ and ʼ. Written as escapes: several look identical.
APOSTROPHES = (
    "\u0027"  # APOSTROPHE
    "\u0060"  # GRAVE ACCENT
    "\u2018"  # LEFT SINGLE QUOTATION MARK
    "\u2019"  # RIGHT SINGLE QUOTATION MARK
    "\u02bb"  # MODIFIER LETTER TURNED COMMA
    "\u02bc"  # MODIFIER LETTER APOSTROPHE
    "\u00b4"  # ACUTE ACCENT
    "\u02b9"  # MODIFIER LETTER PRIME
)

# What the embedding model reads. e5 learned Uzbek from web text, where oʻ/gʻ and the tutuq
# are mostly typed as quotation marks; it ranks texts in that form clearly better than in the
# official one (docs/stage2-experiments.md, 6e).
EMBED_OKINA = "\u2018"  # LEFT SINGLE QUOTATION MARK
EMBED_TUTUQ = "\u2019"  # RIGHT SINGLE QUOTATION MARK

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


def embedding_text(text: str) -> str:
    """Form given to the embedding model, for passages and queries alike."""
    return normalize_text(text).replace(OKINA, EMBED_OKINA).replace(TUTUQ, EMBED_TUTUQ)
