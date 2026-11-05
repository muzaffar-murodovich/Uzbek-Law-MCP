"""``/actinfo/card1/{id}`` (yuridik tahlil kartochkasi) → :class:`DocumentCard`.

Labels come in the interface language (Uzbek Cyrillic without a prefix, Russian under ``/uz/``),
values are always Russian ("Действующий", "Постановление"). See docs/research/lexuz.md, 8.3.
"""

from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from qonunshunos.parser.common import dmy_to_iso, text_of

Status = Literal["in_force", "lost_force", "not_in_force", "suspended", "unknown"]

_FIELDS: dict[str, str] = {
    # Uzbek Cyrillic labels
    "ҳужжат номи": "title",
    "ҳужжат тури": "doc_type",
    "ҳужжат шакли": "form",
    "давлат рўйхат рақами": "registration_number",
    "давлат рўйхатидан ўтган санаси": "registration_date",
    "ҳужжат тили": "language_raw",
    "адлия вазирлиги рўйхатга олиш рақами": "moj_registration_number",
    "адлия вазирлигида рўйхатдан ўтган сана": "moj_registration_date",
    "ҳужжат ҳолати": "status_raw",
    "кучга кириш санаси": "entry_into_force",
    "амал қилиш муддати": "validity",
    "кучини йўқотган санаси": "lost_force_at",
    "кучини йўқотиш сабаби": "lost_force_reason",
    "меъёрийлик характери": "normativity",
    "расмий манба": "official_source",
    "расмий манба нашри №": "official_source_issue",
    # Russian labels
    "наименование акта": "title",
    "вид акта": "doc_type",
    "форма акта": "form",
    "№ гос. регистрации": "registration_number",
    "дата гос. регистрации": "registration_date",
    "язык акта": "language_raw",
    "регистрационный № мю": "moj_registration_number",
    "дата регистрации в мю": "moj_registration_date",
    "статус акта": "status_raw",
    "дата вступления в силу": "entry_into_force",
    "срок действия": "validity",
    "дата прекращения действия": "lost_force_at",
    "причины прекращения действия": "lost_force_reason",
    "характер нормативности": "normativity",
    "официальный источник": "official_source",
    "№ издания официального источника": "official_source_issue",
    "дата опубликования официального источника": "official_source_date",
}
_DATE_FIELDS = {
    "registration_date",
    "moj_registration_date",
    "entry_into_force",
    "lost_force_at",
    "official_source_date",
}

_STATUSES: dict[str, Status] = {
    "действующий": "in_force",
    "amalda": "in_force",
    "амалда": "in_force",
    "утративший силу": "lost_force",
    "kuchini yoʻqotgan": "lost_force",
    "kuchini yo'qotgan": "lost_force",
    "кучини йўқотган": "lost_force",
    "не вступил в силу": "not_in_force",
    "kuchga kirmagan": "not_in_force",
    "кучга кирмаган": "not_in_force",
    "приостановлен": "suspended",
    "действие приостановлено": "suspended",
}
_LANGUAGES = {
    "узбекский (л)": "uz-Latn",
    "узбекский (к)": "uz-Cyrl",
    "русский": "ru",
    "английский": "en",
}


class CardBody(BaseModel):
    """One row of "Ҳужжатни қабул қилган органлар"."""

    organ: str
    position: str | None = None
    person: str | None = None
    adopted_at: str | None = None
    number: str | None = None
    place: str | None = None


class DocumentCard(BaseModel):
    lex_id: int
    title: str | None = None
    doc_type: str | None = None  # "Решения Правительства", "Законодательные акты"
    form: str | None = None  # "Постановление", "Кодекс"
    bodies: list[CardBody] = Field(default_factory=list)
    registration_number: str | None = None
    registration_date: str | None = None
    moj_registration_number: str | None = None
    moj_registration_date: str | None = None
    language: str | None = None
    language_raw: str | None = None
    status: Status = "unknown"
    status_raw: str | None = None
    entry_into_force: str | None = None
    validity: str | None = None
    lost_force_at: str | None = None
    lost_force_reason: str | None = None
    normativity: str | None = None
    official_source: str | None = None
    official_source_issue: str | None = None
    official_source_date: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)  # labels we do not map


def _norm_label(label: str) -> str:
    return " ".join(label.split()).lower()


def parse_card(html: str, lex_id: int) -> DocumentCard:
    soup = BeautifulSoup(html, "lxml")
    values: dict[str, str | None] = {}
    extra: dict[str, str] = {}
    for label_cell in soup.select("td.lbl"):
        value_cell = label_cell.find_next_sibling("td")
        if value_cell is None:
            continue
        label = " ".join(label_cell.get_text(" ").split())
        value = text_of(value_cell) or None
        field = _FIELDS.get(_norm_label(label))
        if field is None:
            if value:
                extra[label] = value
            continue
        values[field] = dmy_to_iso(value) or value if field in _DATE_FIELDS else value

    bodies = []
    for row in soup.select("#bodyTBody tr"):
        cells = [text_of(td) or None for td in row.find_all("td")]
        if len(cells) >= 7 and cells[1]:
            bodies.append(
                CardBody(
                    organ=cells[1],
                    position=cells[2],
                    person=cells[3],
                    adopted_at=dmy_to_iso(cells[4]) or cells[4],
                    number=cells[5],
                    place=cells[6],
                )
            )

    status_raw = values.get("status_raw")
    language_raw = values.get("language_raw")
    return DocumentCard(
        lex_id=lex_id,
        bodies=bodies,
        status=_STATUSES.get(_norm_label(status_raw), "unknown") if status_raw else "unknown",
        language=_LANGUAGES.get(_norm_label(language_raw)) if language_raw else None,
        extra=extra,
        **values,
    )
