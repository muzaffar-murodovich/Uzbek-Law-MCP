from qonunshunos.crawler.rss import parse_rss


def test_parse_rss(fixture_html):
    items = parse_rss(fixture_html("rss.xml"))
    assert [i.lex_id for i in items] == [-8575299, 8574456, -8569963, -8551484]
    law = items[2]
    assert law.title.startswith("Yongʻin xavfsizligi tizimi takomillashtirilayotganligi")
    assert law.info.startswith("Oʻzbekiston Respublikasining Qonuni")
    assert (law.adopted, law.in_force) == ("2026-11-02", "2027-02-05")
