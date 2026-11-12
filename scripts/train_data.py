"""Training pairs for fine-tuning the embedding model and the reranker (OpenAI, see llm.py).

    bash scripts/with_server_db.sh uv run python scripts/train_data.py export \
        --sample 100 --out data/train/batches/b001.jsonl
    uv run python scripts/train_data.py generate data/train/batches/b001.jsonl \
        --model gpt-5.4 --out data/train/answers/b001.gpt-5.4.jsonl
    uv run python scripts/train_data.py merge   # data/train/pairs.jsonl from all answers

For each sampled chunk the LLM writes a question an ordinary citizen would ask (naming the
topic, so the question makes sense without the document) and a formal search query. Claude
subagents answer the same batch files with the same instructions (``SYSTEM``). The chunk is the
positive by construction, so no LLM judge is needed. Documents of every evaluation set
are left out, so evaluation stays honest. Output is JSON lines with the passage text, so
training does not need the database. Re-running appends and skips chunks already done.
"""

import argparse
import json
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.llm import OpenAIChat

EVAL_SETS = sorted(Path("eval").glob("questions*.yaml"))

SYSTEM = """Senga Oʻzbekiston qonun hujjatidan bitta parcha beriladi: hujjat nomi, boʻlim va \
modda (band) sarlavhasi, keyin matn. Ikki narsa yoz.
1. "question": shu parchada javobi bor boʻlgan, yuristi boʻlmagan oddiy fuqaro (yoki \
tadbirkor, xodim) beradigan bitta real savol. Soʻzlashuv tilida, oʻzbek lotin yozuvida, \
hayotiy vaziyat orqali. Rasmiy atamalarni iloji boricha ishlatma. Hujjat nomini va modda \
raqamini aytma. Lekin savolning oʻzidan gap nima haqida ekani tushunilsin: qaysi soha, \
qaysi toʻlov, imtiyoz, xizmat, tashkilot turi yoki vaziyat (masalan, "shu yordam puli" emas, \
"tibbiyot xodimlariga beriladigan bir martalik yordam puli").
2. "query": shu savol boʻyicha qonun matnidan qidirish uchun qisqa ibora, rasmiy yuridik \
tilda, qonun matnlaridagi atamalar bilan (3–10 soʻz).
Agar parcha oddiy odam soʻramaydigan narsa haqida boʻlsa (davlat organlarining ichki \
vakolatlari, kuchga kirish, kuchini yoʻqotgan deb topish, atamalar roʻyxati, xalqaro \
shartnomalar, ijro uchun masʼullar, jadval yoki raqamlar roʻyxati) yoki matndan maʼno \
chiqmasa, skip qil.
Faqat JSON qaytar: {"skip": false, "question": "...", "query": "..."} yoki {"skip": true}"""

# Units people live by: articles of codes and laws, and items of the rules a decree approves
# (its annexes: nizom, tartib, qoidalar, reglament). Decree bodies ("the ministry shall ..."),
# introductions and closing sections are left out.
CHUNKS = """
    SELECT c.id, c.document_id, d.doc_kind
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    JOIN sections s ON s.id = c.section_id
    WHERE d.status = 'in_force' AND d.content = 'html' AND length(c.text) BETWEEN 200 AND 2500
      AND NOT (d.id = ANY(%s))
      AND (s.kind = 'modda' OR (s.kind = 'band' AND cardinality(s.path) > 0))
      AND NOT (array_to_string(s.path, ' ') ~* %s)
      AND d.doc_kind <> 'farmoyish'
    ORDER BY c.id
"""
SKIP_PATH = r"yakunlovchi|oʻtish davri|kuchga kirish|ijro"

# Documents drawn per kind in proportion to the corpus times this weight: a citizen's question
# lands in a code or a law far more often than its share of documents suggests.
KIND_WEIGHT = {"kodeks": 8.0, "konstitutsiya": 4.0, "qonun": 3.0, "buyruq": 1.5}


def eval_documents() -> set[int]:
    docs = set()
    for path in EVAL_SETS:
        items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        items = items["questions"] if isinstance(items, dict) else items
        for item in items:
            for expected in item.get("expected") or []:
                docs.add(int(expected["document"]))
    return docs


def sample_chunks(rows: list[tuple[int, int, str]], n: int, per_doc: int, rng: random.Random):
    """Chunk ids: documents drawn per kind (weighted), up to ``per_doc`` chunks each."""
    by_doc: dict[int, list[int]] = {}
    kind_of: dict[int, str] = {}
    for chunk_id, doc_id, kind in rows:
        by_doc.setdefault(doc_id, []).append(chunk_id)
        kind_of[doc_id] = kind or "boshqa"
    docs_by_kind: dict[str, list[int]] = {}
    for doc_id, kind in kind_of.items():
        docs_by_kind.setdefault(kind, []).append(doc_id)
    weight = {k: len(d) * KIND_WEIGHT.get(k, 1.0) for k, d in docs_by_kind.items()}
    total = sum(weight.values())
    picked = []
    for kind, docs in sorted(docs_by_kind.items()):
        want = max(1, round(n * weight[kind] / total))
        chosen = rng.sample(sorted(docs), min(len(docs), want))
        pool = [
            c
            for doc_id in chosen
            for c in rng.sample(by_doc[doc_id], min(per_doc, len(by_doc[doc_id])))
        ]
        picked.extend(rng.sample(pool, min(want, len(pool))))
    rng.shuffle(picked)
    return picked[:n]


def used_chunks() -> set[int]:
    seen = set()
    for path in Path("data/train/batches").glob("*.jsonl"):
        seen |= {json.loads(line)["chunk_id"] for line in path.open(encoding="utf-8")}
    return seen


def export(args: argparse.Namespace) -> None:
    """Write one batch of sampled chunks (never a chunk of an earlier batch)."""
    settings = Settings.from_env()
    rng = random.Random(args.seed)
    excluded = eval_documents()
    seen = used_chunks()
    with connect(settings.dsn) as conn:
        rows = conn.execute(CHUNKS, (sorted(excluded), SKIP_PATH)).fetchall()
        rows = [r for r in rows if r[0] not in seen]
        ids = sample_chunks(rows, args.sample, args.per_doc, rng)
        sample = conn.execute(
            """
            SELECT c.id, c.document_id, c.section_id, d.doc_kind, s.number, c.heading, c.text
            FROM chunks c JOIN documents d ON d.id = c.document_id
            JOIN sections s ON s.id = c.section_id
            WHERE c.id = ANY(%s) ORDER BY array_position(%s, c.id)
            """,
            (ids, ids),
        ).fetchall()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for chunk_id, doc_id, section_id, kind, number, heading, text in sample:
            record = {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "section_id": section_id,
                "kind": kind,
                "number": number,
                "passage": f"{heading}\n{text}",
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    kinds = Counter(r[3] for r in sample)
    print(f"{len(rows)} eligible chunks, {len(excluded)} eval documents left out; "
          f"wrote {len(sample)} to {args.out}: {dict(kinds)}")  # fmt: skip


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def generate(args: argparse.Namespace) -> None:
    """Answer one batch with an OpenAI model (same format the Claude subagents write)."""
    llm = OpenAIChat(args.model, allow_paid=args.allow_paid)
    batch = read_jsonl(args.batch)
    out_path = args.out or Path("data/train/answers") / f"{args.batch.stem}.{args.model}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["chunk_id"] for r in read_jsonl(out_path)} if out_path.exists() else set()
    todo = [r for r in batch if r["chunk_id"] not in done]

    def ask(row):
        return row, llm.json(SYSTEM, row["passage"])

    kept = skipped = 0
    with ThreadPoolExecutor(args.workers) as pool, out_path.open("a", encoding="utf-8") as out:
        for start in range(0, len(todo), args.workers):
            for row, reply in pool.map(ask, todo[start : start + args.workers]):
                skip = bool(reply.get("skip")) or not reply.get("question")
                record = {
                    "chunk_id": row["chunk_id"],
                    "skip": skip,
                    "question": None if skip else str(reply["question"]).strip(),
                    "query": None if skip else str(reply.get("query") or "").strip(),
                    "model": args.model,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += not skip
                skipped += skip
            out.flush()
    print(f"{out_path}: kept {kept}, skipped {skipped}, tokens {llm.usage}")


_CYRILLIC = re.compile("[Ѐ-ӿ]")


def problems(answer: dict, batch_ids: set[int]) -> list[str]:
    found = []
    if answer.get("chunk_id") not in batch_ids:
        found.append("unknown chunk_id")
    if answer.get("skip"):
        return found
    for field in ("question", "query"):
        text = answer.get(field) or ""
        if len(text.split()) < 3:
            found.append(f"{field} too short")
        if _CYRILLIC.search(text):
            found.append(f"{field} has Cyrillic")
    return found


def merge(args: argparse.Namespace) -> None:
    """Join every answer file with its batch into one training file; report what was dropped."""
    batches = {
        p.stem: {r["chunk_id"]: r for r in read_jsonl(p)}
        for p in Path("data/train/batches").glob("*.jsonl")
    }
    out, dropped, seen = [], Counter(), set()
    for path in sorted(Path("data/train/answers").glob("*.jsonl")):
        batch = batches.get(path.name.split(".", 1)[0], {})
        for answer in read_jsonl(path):
            issues = problems(answer, set(batch))
            if issues:
                dropped.update(issues)
                continue
            if answer.get("skip"):
                dropped["skipped by model"] += 1
                continue
            key = (answer["chunk_id"], answer["question"])
            if key in seen:
                dropped["duplicate"] += 1
                continue
            seen.add(key)
            out.append({**batch[answer["chunk_id"]], **answer})
    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8"
    )
    by_model = Counter(r["model"] for r in out)
    print(f"{len(out)} pairs -> {args.out}; by model {dict(by_model)}; dropped {dict(dropped)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export")
    p.add_argument("--sample", type=int, default=100, help="chunks in the batch")
    p.add_argument("--per-doc", type=int, default=2, help="chunks per sampled document")
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("generate")
    p.add_argument("batch", type=Path)
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--out", type=Path)
    p.add_argument("--workers", type=int, default=6, help="parallel API calls")
    p.add_argument(
        "--allow-paid",
        action="store_true",
        help="keep going on paid tokens once every free allowance is used",
    )
    p = sub.add_parser("merge")
    p.add_argument("--out", type=Path, default=Path("data/train/pairs.jsonl"))
    args = parser.parse_args()
    {"export": export, "generate": generate, "merge": merge}[args.command](args)


if __name__ == "__main__":
    main()
