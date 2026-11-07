"""Shrink a saved lex.uz page into a small test fixture.

Document pages keep <title>, the language buttons, "amendment pending" banners, the edition
dropdown and selected children of #divCont. Every heading before the last kept child is also
kept so that heading paths stay right.

    uv run python scripts/make_fixture.py data/raw/doc.html tests/fixtures/lexuz/x.html \
        --range 0:74 --range 1556:1599 --range -1:

Other pages (card1, search listings) are copied without scripts, styles, selects and svg.
"""

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

HEADING_CLASSES = {
    "TEXT_HEADER_DEFAULT",
    "TEXT_BOLD_CENTER",
    "APPL_BANNER_LANDSCAPE_TITLE",
    "ACT_TITLE_APPL",
}
MAX_BYTES = 100_000
KEEP_UI_BUTTONS = 10


def parse_range(value: str, length: int) -> range:
    start, _, stop = value.partition(":")
    return range(length)[slice(int(start) if start else None, int(stop) if stop else None)]


def shrink_document(soup: BeautifulSoup, ranges: list[str]) -> str:
    cont = soup.find(id="divCont")
    parts = [f"<title>{soup.title.decode_contents() if soup.title else ''}</title>"]
    for link in soup.select(".docContentHeader__item-link"):
        if link.get("id") != "dd3":
            parts.append(str(link))
    parts.extend(str(strip) for strip in soup.select(".lx_strip"))
    dates = soup.find(id="lx_var_t")
    if dates is not None:
        parts.append(str(dates))
    if cont is None:
        pdf = soup.find(id="pdfBody")
        parts.append(str(pdf) if pdf else "")
        parts.extend(str(s) for s in soup.find_all("script") if "PDFObject.embed" in s.text)
    else:
        children = cont.find_all(recursive=False)
        keep: set[int] = set()
        for value in ranges or [":"]:
            keep.update(parse_range(value, len(children)))
        last = max(keep, default=-1)
        for i, child in enumerate(children[: last + 1]):
            if HEADING_CLASSES & set(child.get("class", [])):
                keep.add(i)
        # Interface buttons (lx_elem2) are kept only in the first few elements to save space;
        # that is enough to test that the parser drops them.
        for n, i in enumerate(sorted(keep)):
            if n >= KEEP_UI_BUTTONS:
                for ui in children[i].select(".lx_elem2"):
                    ui.decompose()
        kept = "".join(str(children[i]) for i in sorted(keep))
        parts.append(f'<div id="divCont">{kept}</div>')
    body = "\n".join(parts)
    head = '<!DOCTYPE html>\n<html><head><meta charset="utf-8"></head><body>'
    return f"{head}\n{body}\n</body></html>\n"


def shrink_other(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(["script", "style", "select", "svg", "link", "meta", "noscript"]):
        tag.decompose()
    for selector in ("header", "footer", "nav", ".footer", ".header"):
        for tag in soup.select(selector):
            tag.decompose()
    return str(soup)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--range", action="append", default=[], help="slice of #divCont children")
    args = parser.parse_args()

    soup = BeautifulSoup(args.source.read_text(encoding="utf-8"), "lxml")
    is_document = soup.find(id="divCont") or soup.find(id="pdfBody")
    html = shrink_document(soup, args.range) if is_document else shrink_other(soup)
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(html, encoding="utf-8")
    size = len(html.encode())
    print(f"{args.target}: {size} bytes")
    if size > MAX_BYTES:
        raise SystemExit(f"fixture is larger than {MAX_BYTES} bytes")


if __name__ == "__main__":
    main()
