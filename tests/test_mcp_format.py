import datetime as dt

import pytest

from qonunshunos.mcp import format as fmt
from qonunshunos.mcp.resolve import key, normalize_unit_number, unit_kinds
from qonunshunos.mcp.tools import SectionRow, _find_heading, table_of_contents


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("161", "161"),
        ("161-modda", "161"),
        ("161 modda", "161"),
        ("10¹", "10¹"),
        ("10-1", "10¹"),
        ("10^1", "10¹"),
        ("126-12", "126¹²"),
        ("5-band", "5"),
        ("ст. 15", "15"),
    ],
)
def test_normalize_unit_number(raw, expected):
    assert normalize_unit_number(raw) == expected


def test_number_key_ignores_apostrophes_and_dashes():
    assert key("OʻRQ-642") == key("orq 642") == key("O'RQ–642") == "orq642"
    assert key("PF-60") == "pf60"


def test_unit_kinds_prefer_articles_in_laws():
    assert unit_kinds("kodeks")[0] == "modda"
    assert unit_kinds("vm_qarori")[0] == "band"


def test_paginate_splits_at_lines():
    text = "\n".join(f"{i}. " + "x" * 90 for i in range(100))  # ≈9.5k characters
    first = fmt.paginate(text, 1, size=4000)
    assert first.total == 3 and first.number == 1
    assert first.text.endswith("x") and len(first.text) <= 4000
    assert fmt.paginate(text, 99, size=4000).number == 3  # clamped to the last page
    joined = "\n".join(fmt.paginate(text, n, size=4000).text for n in (1, 2, 3))
    assert joined == text
    assert "page=2" in first.footer("get_article(page={page})")
    assert fmt.paginate("short").footer("x") == ""


def test_paginate_cuts_long_lines():
    page = fmt.paginate("soʻz " * 3000, 1, size=1000)
    assert page.total >= 15 and len(page.text) <= 1000


def test_last_change_picks_latest_link_date():
    extra = {
        "changes": [
            {"text": "(B tahririda — QMMB, 2024)", "links": [{"ondate": "2024-09-21"}]},
            {"text": "(A tahririda — QMMB, 2021)", "links": [{"ondate": "2021-04-21"}]},
        ]
    }
    assert fmt.last_change(extra) == "B tahririda"
    assert fmt.last_change({}) is None


def test_dates_and_labels():
    assert fmt.date_uz(dt.date(2022, 10, 28)) == "28.10.2022"
    assert fmt.date_uz("2022-10-28") == "28.10.2022"
    assert fmt.unit_label("modda", "161", "Bekor qilish") == "161-modda. Bekor qilish"
    assert fmt.unit_label("kirish", None) == "Kirish qismi"


def _row(ord_, kind, number, text, path, title=None):
    return SectionRow(ord_, ord_, kind, None, number, title or text, path, None, text, {})


SECTIONS = [
    _row(0, "boʻlim", "I", "I BOʻLIM. UMUMIY", []),
    _row(1, "bob", "1", "1-bob. Asosiy", ["I BOʻLIM. UMUMIY"]),
    _row(2, "modda", "1", "matn", ["I BOʻLIM. UMUMIY", "1-bob. Asosiy"]),
    _row(3, "modda", "2", "matn", ["I BOʻLIM. UMUMIY", "1-bob. Asosiy"]),
    _row(4, "bob", "2", "2-bob. Shartnoma", ["I BOʻLIM. UMUMIY"]),
    _row(5, "modda", "3", "matn", ["I BOʻLIM. UMUMIY", "2-bob. Shartnoma"]),
]


def test_table_of_contents_has_article_ranges():
    assert table_of_contents(SECTIONS) == [
        "- [#0] I BOʻLIM. UMUMIY — 1–3-moddalar",
        "  - [#1] 1-bob. Asosiy — 1–2-moddalar",
        "  - [#4] 2-bob. Shartnoma — 3-modda",
    ]


@pytest.mark.parametrize(
    ("ref", "ords"),
    [
        ("#4", [4]),
        ("4", [4]),
        ("2-bob", [4]),
        ("I boʻlim", [0]),
        ("I bo'lim", [0]),
        ("shartnoma", [4]),
        ("99-bob", []),
    ],
)
def test_find_heading(ref, ords):
    assert [h.ord for h in _find_heading(SECTIONS, ref)] == ords
