import pytest

from nizom.index.doctype import display_title, doc_kind, restated_title


@pytest.mark.parametrize(
    ("form", "number", "bodies", "kind"),
    [
        ("Закон", "OʻRQ-641", "", "qonun"),
        ("Қонун", "OʻRQ-482", "", "qonun"),
        ("Qonun", "OʻRQ-642", "", "qonun"),
        ("Кодекс", None, "", "kodeks"),
        ("Конституция", None, "", "konstitutsiya"),
        ("Указ", "PF-60", "", "farmon"),
        ("Постановление", "PQ-12", "", "qaror"),
        ("Постановление", "897", "Oʻzbekiston Respublikasi Vazirlar Mahkamasining", "vm_qarori"),
        ("Постановление", "606", "Кабинет Министров Республики Узбекистан", "vm_qarori"),
        ("Постановление", "15", "Toshkent shahar hokimligi", "boshqa"),
        (None, None, "", "boshqa"),
    ],
)
def test_doc_kind(form, number, bodies, kind):
    assert doc_kind(form, number, bodies) == kind


@pytest.mark.parametrize(
    ("title", "kind", "number", "expected"),
    [
        ("Oʻzbekiston Respublikasining Mehnat kodeksi", "kodeks", None, "Mehnat kodeksi"),
        (
            "Oʻzbekiston Respublikasining Maʼmuriy javobgarlik toʻgʻrisidagi kodeksi",
            "kodeks",
            None,
            "Maʼmuriy javobgarlik toʻgʻrisidagi kodeks",
        ),
        (
            "Oʻzbekiston Respublikasi Konstitutsiyasi",
            "konstitutsiya",
            None,
            "Oʻzbekiston Respublikasi Konstitutsiyasi",
        ),
        (
            "Aholi bandligi toʻgʻrisida",
            "qonun",
            "OʻRQ-642",
            "Aholi bandligi toʻgʻrisidagi Qonun (OʻRQ-642)",
        ),
        (
            "Oʻzbekiston Respublikasining fuqaroligi toʻgʻrisida",
            "qonun",
            "OʻRQ-610",
            "Oʻzbekiston Respublikasining fuqaroligi toʻgʻrisidagi Qonun (OʻRQ-610)",
        ),
        (
            "Ijtimoiy karta tizimini joriy etish chora-tadbirlari",
            "vm_qarori",
            "897",
            "Vazirlar Mahkamasi qarori 897: Ijtimoiy karta tizimini joriy etish chora-tadbirlari",
        ),
    ],
)
def test_display_title(title, kind, number, expected):
    assert display_title(title, kind, number) == expected


def test_display_title_clips_long_names():
    title = "Juda uzun nom " * 20
    assert len(display_title(title, "qaror", "PQ-1")) <= 160


def test_restated_title_names_the_act_set_out_anew():
    intro = "… Qonuniga oʻzgartishlar kiritilib, u yangi tahrirda bayon etilsin."
    title = (
        "“Prokuratura toʻgʻrisida”gi Oʻzbekiston Respublikasi Qonuniga oʻzgartishlar va "
        "qoʻshimchalar kiritish haqida"
    )
    assert restated_title(title, "257-II", intro, 58) == (
        "Prokuratura toʻgʻrisidagi Qonun (257-II tahririda)"
    )
    nizom = "“Sudyalarning malaka hayʼatlari toʻgʻrisida”gi nizomga oʻzgartish kiritish haqida"
    assert restated_title(nizom, "OʻRQ-368", "uning yangi tahriri tasdiqlansin", 30) == (
        "Sudyalarning malaka hayʼatlari toʻgʻrisidagi Nizom (OʻRQ-368 tahririda)"
    )
    tili = (
        "“Oʻzbekiston Respublikasining Davlat tili haqida”gi Qonuniga oʻzgartishlar kiritish haqida"
    )
    assert restated_title(tili, "167-I", intro, 24) == (
        "Oʻzbekiston Respublikasining Davlat tili haqidagi Qonun (167-I tahririda)"
    )
    # A few amended articles, or no restatement: the act keeps its own title.
    assert restated_title(title, "257-II", intro, 3) is None
    assert restated_title(title, "257-II", "3-modda oʻz kuchini yoʻqotgan", 58) is None
    assert restated_title("Aholi bandligi toʻgʻrisida", "OʻRQ-642", intro, 58) is None
