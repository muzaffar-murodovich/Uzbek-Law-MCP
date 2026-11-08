from qonunshunos.cli import main


def test_main_without_command_prints_help(capsys):
    assert main([]) == 0
    assert "qonunshunos" in capsys.readouterr().out


def test_parse_all_reparses_scope_pages_only(tmp_path, fixture_html, capsys):
    import json

    from qonunshunos.crawler.full import scope_dir
    from qonunshunos.crawler.pipeline import Workspace

    ws = Workspace(tmp_path)
    for lex_id in (-1, -2, -3):  # -3: an RSS act outside the scope
        ws.raw.save("docs", lex_id, fixture_html("doc_pf60.html"), "https://lex.uz/docs/x", 200)
    folder = scope_dir(ws)
    folder.mkdir(parents=True)
    rows = [
        {"lex_id": -1, "title": "A"},
        {"lex_id": -2, "title": "B"},
        {"lex_id": -9, "title": "C"},
    ]
    payload = {"minor": "N", "year": 2020, "expected": 3, "rows": rows}
    (folder / "N-2020.json").write_text(json.dumps(payload))

    assert main(["--data-dir", str(tmp_path), "parse", "--all"]) == 0
    assert "2 documents, 0 failed" in capsys.readouterr().out
    assert ws.parsed_path(-1).exists() and not ws.parsed_path(-3).exists()
