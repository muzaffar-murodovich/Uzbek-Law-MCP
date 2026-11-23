"""Evaluation questions answered by lawyers on advice.uz ("Madad" NNT), labelled from the
articles their answers cite (docs/stage2-experiments.md 6l).

The question and answer texts stay in ``data/`` (not in git): the repo keeps only ids, source
URLs and labels (``eval/labels_advice.yaml``). ``questions`` rebuilds the full question file
from both, for ``qonunshunos eval``.

    uv run python scripts/real_eval.py fetch        # advice.uz -> data/eval/real/advice/raw/
    uv run python scripts/real_eval.py extract      # raw pages -> items.json (question, answer)
    # labels: subagents, see data/eval/real/advice/LABEL_INSTRUCTIONS.md
    uv run python scripts/blind_eval.py build data/eval/real/advice/labels/*.json \
        --out data/eval/real/questions_advice.yaml
    uv run python scripts/real_eval.py strip        # -> eval/labels_advice.yaml (no texts)
    uv run python scripts/real_eval.py questions    # labels + items -> full question file
"""

import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

import yaml

SITE = "https://advice.uz"
ROOT = Path("data/eval/real/advice")
RAW = ROOT / "raw"
ITEMS = ROOT / "items.json"
FULL = Path("data/eval/real/questions_advice.yaml")
LABELS = Path("eval/labels_advice.yaml")
HEADERS = {"User-Agent": "QonunshunosBot/0.1"}
PAUSE = 2.0  # seconds between requests, one at a time


def get(url: str, cache: Path) -> str:
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    time.sleep(PAUSE)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=40) as response:
        text = response.read().decode("utf-8", "replace")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch(args: argparse.Namespace) -> None:
    """Every category page, then the documents that are questions or question-answer lists."""
    regulations = get(f"{SITE}/oz/page/regulations", RAW / "regulations.html")
    categories = sorted(set(re.findall(r"/oz/category/(\d+)", regulations)), key=int)
    wanted: dict[str, str] = {}
    for category in categories:
        page = get(f"{SITE}/oz/category/{category}", RAW / f"category-{category}.html")
        for doc, label in re.findall(r'/oz/document/(\d+)"[^>]*>(.*?)</a>', page, re.S):
            title = text_of(label)
            if title.rstrip().endswith("?") or "savol" in title.lower():
                wanted[doc] = title
    print(f"{len(categories)} categories, {len(wanted)} documents to fetch", flush=True)
    for n, doc in enumerate(sorted(wanted, key=int), start=1):
        get(f"{SITE}/oz/document/{doc}", RAW / f"document-{doc}.html")
        if n % 25 == 0:
            print(f"{n}/{len(wanted)}", flush=True)


def body(page: str) -> tuple[str, list[str]]:
    """Title and the paragraphs of the document text."""
    title = text_of(re.search(r'<h3 class="page-header">(.*?)</h3>', page, re.S).group(1))
    start = page.find('<div class="page-document-content')
    end = page.find("Maqola foydali", start)
    content = page[start : end if end > 0 else None]
    blocks = re.split(r"</p>|<br\s*/?>|</li>|</h\d>|</div>", content)
    return title, [t for t in (text_of(b) for b in blocks) if t]


QUESTION = re.compile(r"^(?:\d{1,3}\s*[.)]\s*)?(?P<q>.{12,400}\?)$")


def extract(args: argparse.Namespace) -> None:
    """One item per question: a document titled as a question, or each question in a list."""
    items = []
    for path in sorted(RAW.glob("document-*.html"), key=lambda p: int(p.stem.split("-")[1])):
        doc = path.stem.split("-")[1]
        title, paragraphs = body(path.read_text(encoding="utf-8"))
        url = f"{SITE}/oz/document/{doc}"
        if title.rstrip().endswith("?"):
            answer = [p for p in paragraphs if p.rstrip(" ?") != title.rstrip(" ?")]
            items.append({"id": f"adv-{doc}", "url": url, "question": title, "answer": answer})
            continue
        current = None
        for p in paragraphs:
            match = QUESTION.match(p)
            if match:
                current = {
                    "id": f"adv-{doc}-{len([i for i in items if i['url'] == url]) + 1}",
                    "url": url,
                    "question": match.group("q").strip(),
                    "answer": [],
                }
                items.append(current)
            elif current is not None:
                current["answer"].append(p)
    items = [i for i in items if i["answer"]]
    for i in items:
        i["answer"] = "\n".join(i["answer"])
        i["cites"] = bool(re.search(r"\d+[¹²³⁴⁵⁶⁷⁸⁹]*\s*-\s*modda|moddas", i["answer"]))
    ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    cited = sum(i["cites"] for i in items)
    print(f"{len(items)} questions, {cited} answers cite an article -> {ITEMS}")


def strip(args: argparse.Namespace) -> None:
    """Labels without the texts, for git."""
    items = {i["id"]: i for i in json.loads(ITEMS.read_text(encoding="utf-8"))}
    full = yaml.safe_load(FULL.read_text(encoding="utf-8"))
    out = [
        {"id": q["id"], "url": items[q["id"]]["url"], "expected": q["expected"], "tags": q["tags"]}
        for q in full
    ]
    LABELS.write_text(
        "# advice.uz questions (scripts/real_eval.py): ids, sources and labels only; the texts\n"
        "# stay in data/ (questions rebuilds data/eval/real/questions_advice.yaml).\n"
        + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"{len(out)} labelled questions -> {LABELS}")


def questions(args: argparse.Namespace) -> None:
    items = {i["id"]: i for i in json.loads(ITEMS.read_text(encoding="utf-8"))}
    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))
    out = [
        {
            "id": q["id"],
            "question": items[q["id"]]["question"],
            **{k: q[k] for k in ("expected", "tags")},
        }
        for q in labels
    ]
    FULL.parent.mkdir(parents=True, exist_ok=True)
    FULL.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100))
    print(f"{len(out)} questions -> {FULL}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "extract", "strip", "questions"):
        sub.add_parser(name)
    args = parser.parse_args()
    {"fetch": fetch, "extract": extract, "strip": strip, "questions": questions}[args.command](args)


if __name__ == "__main__":
    main()
