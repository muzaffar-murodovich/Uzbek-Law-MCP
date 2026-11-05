from qonunshunos.parser.card import parse_card


def test_card_in_force(fixture_html):
    card = parse_card(fixture_html("card1_in_force.html"), -8569965)
    assert card.title.startswith("Texnogen xususiyatli favqulodda vaziyatlar")
    assert (card.doc_type, card.form) == ("Решения Правительства", "Постановление")
    assert (card.status, card.status_raw) == ("in_force", "Действующий")
    assert (card.language, card.language_raw) == ("uz-Latn", "Узбекский (Л)")
    assert card.entry_into_force == "2026-11-04"
    assert card.validity == "Бессрочный"
    assert card.lost_force_at is None
    assert card.official_source_issue == "09/26/606/1096"
    assert card.official_source_date == "2026-11-04"
    assert len(card.bodies) == 1
    body = card.bodies[0]
    assert body.organ == "Кабинет Министров Республики Узбекистан"
    assert (body.person, body.adopted_at, body.number) == ("А. Арипов", "2026-11-03", "606")


def test_card_lost_force(fixture_html):
    card = parse_card(fixture_html("card1_lost_force.html"), -142859)
    assert card.title == "Oʻzbekiston Respublikasining Mehnat kodeksi"  # apostrophe normalized
    assert card.form == "Кодекс"
    assert card.status == "lost_force"
    assert card.entry_into_force == "1996-04-01"
    assert card.lost_force_at == "2023-04-30"
    assert card.lost_force_reason is None
    assert card.extra["Год издания официального источника"] == "1996"


def test_card_russian_labels():
    html = """<table><tr><td class="lbl">Статус акта</td><td class="codL">Утративший силу</td>
    <td class="lbl">Дата прекращения действия</td><td class="codR">01.01.2020</td></tr></table>"""
    card = parse_card(html, -1)
    assert (card.status, card.lost_force_at) == ("lost_force", "2020-01-01")


def test_card_unknown_status():
    html = (
        '<table><tr><td class="lbl">Статус акта</td><td class="codL">Что-то новое</td></tr></table>'
    )
    card = parse_card(html, -1)
    assert (card.status, card.status_raw) == ("unknown", "Что-то новое")
