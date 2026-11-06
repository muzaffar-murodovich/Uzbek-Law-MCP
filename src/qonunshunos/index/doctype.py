"""Normalized document kind and human-readable title.

card1 arrives in Russian, Uzbek Cyrillic or Uzbek Latin depending on the page, so the raw form
("Закон", "Қонун", "Qonun") is mapped onto one small vocabulary used by the tools.
"""

import re

from qonunshunos.text.normalize import fold

KINDS = (
    "konstitutsiya",
    "kodeks",
    "qonun",
    "farmon",  # Presidential decree (PF)
    "qaror",  # Presidential resolution (PQ)
    "vm_qarori",  # Cabinet of Ministers resolution
    "farmoyish",
    "buyruq",  # ministry / agency order
    "boshqa",
)

LABELS = {
    "konstitutsiya": "Konstitutsiya",
    "kodeks": "Kodeks",
    "qonun": "Qonun",
    "farmon": "Prezident farmoni",
    "qaror": "Prezident qarori",
    "vm_qarori": "Vazirlar Mahkamasi qarori",
    "farmoyish": "Farmoyish",
    "buyruq": "Buyruq",
    "boshqa": "Hujjat",
}

# Folded (lowercase, Latin, no apostrophes) card1 form → kind; "qaror" is refined by the body.
_FORMS = {
    "конституция": "konstitutsiya",
    "конституцияси": "konstitutsiya",
    "konstitutsiya": "konstitutsiya",
    "кодекс": "kodeks",
    "кодекси": "kodeks",
    "kodeks": "kodeks",
    "закон": "qonun",
    "қонун": "qonun",
    "qonun": "qonun",
    "указ": "farmon",
    "фармон": "farmon",
    "farmon": "farmon",
    "постановление": "qaror",
    "қарор": "qaror",
    "qaror": "qaror",
    "распоряжение": "farmoyish",
    "фармойиш": "farmoyish",
    "farmoyish": "farmoyish",
    "приказ": "buyruq",
    "буйруқ": "buyruq",
    "buyruq": "buyruq",
}

_CABINET = ("vazirlar mahkamasi", "кабинет министров", "вазирлар маҳкамаси")
_PRESIDENT = ("prezident", "президент")


def doc_kind(form: str | None, number: str | None = None, bodies: str = "") -> str:
    """Kind from the card1 form; resolutions split into Presidential and Cabinet ones."""
    kind = _FORMS.get(fold(form or "").strip(), "boshqa")
    if kind != "qaror":
        return kind
    text = fold(bodies)
    if any(b in text for b in _CABINET):
        return "vm_qarori"
    if fold(number or "").startswith(("pq", "пп")) or any(b in text for b in _PRESIDENT):
        return "qaror"
    return "boshqa"


_PREFIX_RE = re.compile(r"^Oʻzbekiston Respublikasining\s+(?=[A-Z])")
_ABOUT_END = "toʻgʻrisida"
MAX_TITLE = 160


def _clip(text: str, size: int = MAX_TITLE) -> str:
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


def display_title(title: str, kind: str, number: str | None = None) -> str:
    """Readable name: "Mehnat kodeksi", "Aholi bandligi toʻgʻrisidagi Qonun (OʻRQ-642)", ...

    "Oʻzbekiston Respublikasining" is dropped only before a capitalized name ("… Mehnat
    kodeksi"); in "Oʻzbekiston Respublikasining fuqaroligi toʻgʻrisida" it is part of the name.
    """
    title = " ".join(title.split())
    if kind in ("konstitutsiya", "kodeks"):
        name = _PREFIX_RE.sub("", title)
        name = name.replace("toʻgʻrisidagi kodeksi", "toʻgʻrisidagi kodeks")
        return _clip(name[:1].upper() + name[1:])
    label = LABELS.get(kind, "Hujjat")
    suffix = f" ({number})" if number else ""
    if title.endswith(_ABOUT_END) and len(title) + len(label) + len(suffix) + 3 <= MAX_TITLE:
        return f"{title}gi {label}{suffix}"
    prefix = f"{label} {number}" if number else label
    return f"{prefix}: {_clip(title, MAX_TITLE - len(prefix) - 2)}"
