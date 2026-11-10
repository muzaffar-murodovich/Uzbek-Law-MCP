"""LLM-made evaluation data (OpenAI, see ``qonunshunos.llm``).

    uv run python scripts/llm_eval.py rephrase   # eval/alt_llm.json: formal search queries
    uv run python scripts/llm_eval.py generate   # eval/questions_llm.yaml: new questions
    uv run python scripts/llm_eval.py judge      # add other articles that answer them
    uv run python scripts/llm_eval.py clarity    # tag questions aniq / noaniq

``rephrase`` imitates the assistant that calls ``search_law``: it sees only the user's
question (never the article) and writes formal search queries. ``generate`` samples articles
from the database and asks for a question an ordinary citizen would ask about each one.
``clarity`` marks questions that do not say what they are about ("shu yordam puli"): written
from one clause, they fit dozens of documents in the full corpus and no search can answer them.
"""

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.evaluation import load_questions
from qonunshunos.llm import OpenAIChat

REPHRASE_SYSTEM = """Sen Oʻzbekiston qonunchiligi boʻyicha savollarga javob beradigan AI \
yordamchisan. Senda lex.uz bazasi boʻyicha qidiruv vositasi bor: u qonun matnidagi soʻzlar va \
maʼno boʻyicha qidiradi. Foydalanuvchining savolini olib, qidiruv uchun 2 ta qisqa ibora yoz: \
rasmiy yuridik oʻzbek tilida (lotin yozuvi), qonun matnlarida ishlatiladigan atamalar bilan. \
Modda raqamlarini yoki hujjat raqamlarini oʻylab topma. \
Faqat JSON qaytar: {"queries": ["...", "..."]}"""

GENERATE_SYSTEM = """Senga Oʻzbekiston qonun hujjatidan bitta modda (yoki band) beriladi. \
Shu matnda javobi bor boʻlgan, yuristi boʻlmagan oddiy fuqaro beradigan bitta real savol yoz.
Talablar:
- soʻzlashuv tilida, oʻzbek lotin yozuvida, odatda hayotiy vaziyat orqali;
- matndagi rasmiy atamalarni iloji boricha ishlatma (odam ularni bilmaydi);
- hujjat nomini va modda raqamini aytma;
- savolning javobi aynan shu matnda boʻlsin.
Agar matn oddiy odam soʻramaydigan narsa haqida boʻlsa (davlat organlarining vakolatlari, \
qonunning kuchga kirishi, atamalar, xalqaro shartnomalar, moliyalashtirish va hokazo), skip qil.
Faqat JSON qaytar: {"skip": false, "question": "..."} yoki {"skip": true}"""


def rephrase(args: argparse.Namespace) -> None:
    llm = OpenAIChat(args.model, allow_paid=args.allow_paid)
    out = args.out
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    todo = [q for q in load_questions(args.questions) if q.id not in done]
    # Independent API calls: run ``workers`` at a time and save after each batch.
    with ThreadPoolExecutor(args.workers) as pool:
        for start in range(0, len(todo), args.workers):
            batch = todo[start : start + args.workers]
            replies = pool.map(lambda q: llm.json(REPHRASE_SYSTEM, q.question), batch)
            for q, reply in zip(batch, replies, strict=True):
                done[q.id] = [s for s in reply.get("queries", []) if isinstance(s, str)][:2]
                print(q.id, done[q.id], flush=True)
            out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    print("tokens:", llm.usage)


ELIGIBLE = """
    SELECT s.id, s.document_id, d.doc_kind
    FROM sections s JOIN documents d ON d.id = s.document_id
    WHERE s.kind IN ('modda', 'band') AND s.number IS NOT NULL
      AND length(s.text) BETWEEN 300 AND 3000 AND d.status = 'in_force' AND d.content = 'html'
    ORDER BY s.id
"""


def stratified(rows: list[tuple[int, int, str]], n: int, minimum: int, rng: random.Random):
    """Section ids, one per random document; documents drawn per kind in proportion to how
    many documents of that kind there are (at least ``minimum`` per kind)."""
    by_doc: dict[int, list[int]] = {}
    kind_of: dict[int, str] = {}
    for section_id, doc_id, kind in rows:
        by_doc.setdefault(doc_id, []).append(section_id)
        kind_of[doc_id] = kind
    docs_by_kind: dict[str, list[int]] = {}
    for doc_id, kind in kind_of.items():
        docs_by_kind.setdefault(kind or "boshqa", []).append(doc_id)
    total = sum(len(d) for d in docs_by_kind.values())
    picked = []
    for _kind, docs in sorted(docs_by_kind.items()):
        want = min(len(docs), max(minimum, round(n * len(docs) / total)))
        for doc_id in rng.sample(docs, want):
            picked.append(rng.choice(by_doc[doc_id]))
    rng.shuffle(picked)
    return picked


def generate(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    rng = random.Random(args.seed)
    llm = OpenAIChat(args.model, allow_paid=args.allow_paid)
    out = args.out
    items = yaml.safe_load(out.read_text(encoding="utf-8")) if out.exists() else []
    seen = {(i["expected"][0]["document"], i["expected"][0]["article"]) for i in items}
    with connect(settings.dsn) as conn:
        rows = conn.execute(ELIGIBLE).fetchall()
        if args.by_kind:
            ids = stratified(rows, args.sample, args.min_per_kind, rng)
        else:
            ids = [r[0] for r in rng.sample(rows, min(args.sample, len(rows)))]
        sample = conn.execute(
            """
            SELECT s.document_id, d.display_title, d.doc_kind, s.number, s.title, s.text, s.path
            FROM sections s JOIN documents d ON d.id = s.document_id
            WHERE s.id = ANY(%s) ORDER BY array_position(%s, s.id)
            """,
            (ids, ids),
        ).fetchall()

    def ask(row):
        _doc, _short, _kind, number, title, text, _path = row
        heading = f"{number}-modda. {title}" if title else f"{number}."
        return row, llm.json(GENERATE_SYSTEM, f"{heading}\n{text}")

    todo = [r for r in sample if (r[0], r[3]) not in seen]
    # Independent API calls: run ``workers`` at a time, keep the sample order for stable ids.
    with ThreadPoolExecutor(args.workers) as pool:
        for start in range(0, len(todo), args.workers):
            if len(items) >= args.limit:
                break
            for row, reply in pool.map(ask, todo[start : start + args.workers]):
                doc_id, short, kind, number, _title, _text, path = row
                if len(items) >= args.limit or reply.get("skip") or not reply.get("question"):
                    continue
                items.append(
                    {
                        "id": f"{args.id_prefix}-{len(items) + 1:03d}",
                        "question": reply["question"].strip(),
                        # Band numbers repeat across a decree and its Nizoms: pin the path.
                        "expected": [
                            {"document": doc_id, "article": number, "within": " > ".join(path)}
                        ],
                        "tags": ["llm", kind or "boshqa"],
                        "source": short,
                    }
                )
                print(items[-1]["id"], kind, short[:50], number, "|", items[-1]["question"],
                      flush=True)  # fmt: skip
            out.write_text(
                "# Generated by scripts/llm_eval.py generate (OpenAI). Expected = source article.\n"
                + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
                encoding="utf-8",
            )
    print("tokens:", llm.usage)


JUDGE_SYSTEM = """Sen tajribali oʻzbek yuristisan. Senga fuqaroning savoli va qonun hujjatlaridan \
bir nechta raqamlangan modda beriladi. Qaysi moddalar savolga bevosita javob beradi, yaʼni \
yurist javobda aynan shu moddaga havola qilardi? Faqat umumiy yoki yondosh mavzudagi moddalarni \
tanlama. Faqat JSON qaytar: {"relevant": [raqamlar]}"""


def judge(args: argparse.Namespace) -> None:
    """Add articles that also answer a question (pooled relevance judgments)."""
    import threading

    from qonunshunos.evaluation import Expected
    from qonunshunos.index.embed import Embedder
    from qonunshunos.search.hybrid import search

    settings = Settings.from_env()
    llm = OpenAIChat(args.model, allow_paid=args.allow_paid)
    items = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    embedder = Embedder(settings.model_dir)
    alt = json.loads(args.alt_file.read_text(encoding="utf-8")) if args.alt_file else {}
    local = threading.local()  # psycopg connections are not shared between threads
    opened = []

    def conn():
        if not hasattr(local, "conn"):
            local.conn = connect(settings.dsn)
            opened.append(local.conn)
        return local.conn

    def judge_one(item: dict) -> list[dict]:
        db = conn()
        hits = search(db, embedder, item["question"], alt.get(item["id"], []), limit=args.depth)
        expected = [
            Expected(int(e["document"]), str(e["article"]), e.get("within"))
            for e in item["expected"]
        ]
        pool = [
            h
            for h in hits
            if not any(e.matches(h.document_id, h.unit_number, h.path) for e in expected)
        ]
        if not pool:
            return []
        texts = []
        for n, hit in enumerate(pool, start=1):
            body = db.execute("SELECT text FROM sections WHERE id = %s", (hit.section_id,))
            label = f"{hit.document}, {hit.unit_number}-{hit.kind}. {hit.unit_title or ''}"
            texts.append(f"[{n}] {label}\n{body.fetchone()[0][: args.chars]}")
        reply = llm.json(JUDGE_SYSTEM, f"Savol: {item['question']}\n\n" + "\n\n".join(texts))
        added = []
        for n in reply.get("relevant", []):
            if isinstance(n, int) and 1 <= n <= len(pool):
                hit = pool[n - 1]
                added.append(
                    {
                        "document": hit.document_id,
                        "article": hit.unit_number,
                        "within": " > ".join(hit.path),
                        "judged": "alt" if args.alt_file else True,
                    }
                )
        return added

    # With --alt-file the pool is what the assistant's formal queries find: a second pass
    # over questions judged on the raw question only. Unclear questions are left out.
    done_key = "judged_alt" if args.alt_file else "judged"
    todo = [
        item
        for item in items
        if not item.get(done_key) and not (args.alt_file and "noaniq" in item.get("tags", []))
    ]
    if args.missed_in:  # enough for R@10: a question that already hits stays a hit
        ranks = json.loads(args.missed_in.read_text(encoding="utf-8"))["questions"]
        todo = [item for item in todo if ranks[item["id"]]["ranks"]["hybrid"] is None]
    try:
        with ThreadPoolExecutor(args.workers) as pool:
            for start in range(0, len(todo), args.workers):
                batch = todo[start : start + args.workers]
                for item, added in zip(batch, pool.map(judge_one, batch), strict=True):
                    item["expected"].extend(added)
                    item[done_key] = True
                    for e in added:
                        print(item["id"], "+", e["document"], e["article"], flush=True)
                args.questions.write_text(
                    YAML_HEADER
                    + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
                    encoding="utf-8",
                )
    finally:
        for c in opened:
            c.close()
    print("tokens:", llm.usage)


YAML_HEADER = (
    "# Generated by scripts/llm_eval.py generate (OpenAI). Expected = source article;\n"
    "# entries with judged: true were added by scripts/llm_eval.py judge.\n"
)

CLARITY_SYSTEM = """Qidiruv tizimini baholash uchun savollar toʻplami tekshirilmoqda. Har bir \
savol Oʻzbekiston qonunchiligidagi bitta hujjatning bitta bandi asosida yozilgan. Senga savol va \
oʻsha hujjatning nomi (boʻlim yoʻli bilan) beriladi. Bazada 15 mingdan ortiq hujjat bor.
Savol "aniq" boʻladi, agar hujjatni koʻrmagan yurist savolning oʻzidan gap aynan nima haqida \
ekanini (qaysi toʻlov, imtiyoz, tanlov, xizmat, tashkilot turi yoki soha) tushunib, shu hujjat \
mavzusini izlay olsa. Savol "noaniq" boʻladi, agar hujjat tor mavzuga tegishli boʻlib, savolda \
shu mavzuni koʻrsatadigan asosiy belgi aytilmagan boʻlsa (masalan, "shu yordam puli", "tanlov", \
"ariza", "birja" deyilgan, lekin qaysi biri ekani nomaʼlum) va savol oʻnlab boshqa hujjatlarga \
ham birdek mos kelsa. Savol soʻzlashuv tilida yozilgani yoki rasmiy atamalar yoʻqligi uni \
noaniq qilmaydi.
Faqat JSON qaytar: {"clear": true} yoki {"clear": false, "missing": "savolda nima aytilmagan"}"""


def clarity(args: argparse.Namespace) -> None:
    """Tag each question ``aniq`` or ``noaniq`` (with what is missing); eval reports both."""
    llm = OpenAIChat(args.model, allow_paid=args.allow_paid)
    items = yaml.safe_load(args.questions.read_text(encoding="utf-8"))

    def ask(item: dict) -> dict:
        within = item["expected"][0].get("within") or ""
        prompt = f"Savol: {item['question']}\n\nHujjat: {item.get('source', '')}\n{within}"
        return llm.json(CLARITY_SYSTEM, prompt)

    todo = [item for item in items if not {"aniq", "noaniq"} & set(item.get("tags", []))]
    with ThreadPoolExecutor(args.workers) as pool:
        for start in range(0, len(todo), args.workers):
            batch = todo[start : start + args.workers]
            for item, reply in zip(batch, pool.map(ask, batch), strict=True):
                clear = reply.get("clear") is not False
                item.setdefault("tags", []).append("aniq" if clear else "noaniq")
                if not clear:
                    item["missing"] = str(reply.get("missing", ""))
                print(item["id"], "aniq" if clear else f"noaniq: {item['missing']}", flush=True)
            args.questions.write_text(
                YAML_HEADER + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
                encoding="utf-8",
            )
    print("tokens:", llm.usage)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("rephrase")
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    p.add_argument("--out", type=Path, default=Path("eval/alt_llm.json"))
    p.add_argument("--workers", type=int, default=6, help="parallel API calls")
    p = sub.add_parser("judge")
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--questions", type=Path, default=Path("eval/questions_llm.yaml"))
    p.add_argument("--depth", type=int, default=5, help="top hits to judge")
    p.add_argument("--chars", type=int, default=1200, help="article text shown to the judge")
    p.add_argument("--alt-file", type=Path, help="JSON {id: [queries]}: judge again with them")
    p.add_argument("--missed-in", type=Path, help="eval result: only questions hybrid missed")
    p.add_argument("--workers", type=int, default=6, help="parallel searches and API calls")
    p = sub.add_parser("clarity")
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--questions", type=Path, default=Path("eval/questions_llm_full.yaml"))
    p.add_argument("--workers", type=int, default=6, help="parallel API calls")
    p = sub.add_parser("generate")
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--sample", type=int, default=400, help="articles to try")
    p.add_argument("--limit", type=int, default=100, help="questions to keep")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, default=Path("eval/questions_llm.yaml"))
    p.add_argument("--id-prefix", default="llm")
    p.add_argument(
        "--by-kind",
        action="store_true",
        help="one article per random document, "
        "documents drawn per kind in proportion to the corpus",
    )
    p.add_argument("--min-per-kind", type=int, default=5)
    p.add_argument("--workers", type=int, default=6, help="parallel API calls")
    for p in sub.choices.values():
        p.add_argument(
            "--allow-paid",
            action="store_true",
            help="keep going on paid tokens once every free allowance is used",
        )
    args = parser.parse_args()
    {"rephrase": rephrase, "generate": generate, "judge": judge, "clarity": clarity}[args.command](
        args
    )


if __name__ == "__main__":
    main()
