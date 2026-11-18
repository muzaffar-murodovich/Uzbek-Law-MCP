"""Build a word → lemma table for full-text search with the uzmorph analyser (offline).

uzmorph (Apertium uzb + a ranker, GPL-3.0, https://huggingface.co/javohirmat/uzmorph) needs
lttoolbox's ``lt-proc``. It is not a dependency of the project: run this script in its own
environment, with the project's ``src`` on the path for ``fold``:

    uv venv /tmp/uzm/.venv && uv pip install --python /tmp/uzm/.venv/bin/python \
        https://huggingface.co/javohirmat/uzmorph/resolve/main/dist/uzmorph-0.9.0-py3-none-any.whl
    PYTHONPATH=src /tmp/uzm/.venv/bin/python scripts/build_lemmas.py \
        data/embed/chunk_texts_all.json.gz --out data/fts/lemmas.tsv \
        --package src/qonunshunos/text/lemmas.tsv.gz

Only the table (data) is used by the service, never uzmorph itself. Keys and lemmas are in the
FTS form: ``fold`` and without the ʻ ʼ marks (``text.fts.terms``). ``--out``: ``word<TAB>lemma
<TAB>count``, most frequent first; words uzmorph cannot analyse get an empty lemma.
``--package``: the rows the search needs (``text.fts._lemmas``), the words whose stem changes.

Verbs (UPOS VERB, AUX) get no lemma and keep the suffix stripper: their root merges voices and
forms with other meanings (solinadigan → sol). uzmorph also strips derivational suffixes
that change the meaning (raqamli → raqam, ishsiz → ish, beruvchi → ber, taqiqlanmagan →
taqiqlan); ``keep_derivation`` puts them back.
"""

import argparse
import gzip
import json
import time
from collections import Counter
from pathlib import Path

import uzmorph

from qonunshunos.text.fts import _DROP, _WORD_RE, stem
from qonunshunos.text.normalize import fold

# Kept on the lemma when uzmorph strips them: agent nouns, -li / -siz adjectives, -lik nouns,
# negation (-ma), birov. Longest first.
DERIVATIONAL = ("chilik", "uvchi", "ovchi", "chi", "lik", "siz", "li", "ma", "ov")


def key(word: str) -> str:
    return word.translate(_DROP)


def keep_derivation(word: str, lemma: str) -> str:
    """``lemma`` plus the derivational suffix that follows it in ``word``, if any."""
    if lemma and word.startswith(lemma):
        rest = word[len(lemma) :]
        for suffix in DERIVATIONAL:
            if rest.startswith(suffix):
                return lemma + suffix
    return lemma


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("texts", type=Path, help="json.gz {chunk id: text}")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path, help="gzip table for text/fts.py")
    parser.add_argument("--batch", type=int, default=5000)
    args = parser.parse_args()

    with gzip.open(args.texts, "rt", encoding="utf-8") as f:
        texts = json.load(f)
    counts: Counter[str] = Counter()
    for text in texts.values():
        counts.update(w for w in _WORD_RE.findall(fold(text)) if not w.isdigit())
    words = [w for w, _ in counts.most_common()]
    print(f"{len(texts)} chunks, {len(words)} distinct words", flush=True)

    lemma: dict[str, str] = {}
    started = time.monotonic()
    for start in range(0, len(words), args.batch):
        part = words[start : start + args.batch]
        tokens = [t for t in uzmorph.analyze("\n".join(part)) if t.is_word]
        found = {
            fold(t.text): fold(t.best.lemma)
            for t in tokens
            if t.best and t.best.lemma and t.best.upos not in ("VERB", "AUX")
        }
        for w in part:
            lemma[w] = found.get(w, "")
        print(f"{start + len(part)}/{len(words)} {time.monotonic() - started:.0f}s", flush=True)

    # Several spellings can share one FTS key (the ʻ ʼ marks are dropped): the most frequent wins.
    table: dict[str, tuple[str, int]] = {}
    for w in words:
        k = key(w)
        if k not in table:
            table[k] = (keep_derivation(k, key(lemma[w])), counts[w])
        else:
            table[k] = (table[k][0], table[k][1] + counts[w])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for k, (lem, n) in sorted(table.items(), key=lambda x: -x[1][1]):
            f.write(f"{k}\t{lem}\t{n}\n")
    unknown = sum(1 for lem, _ in table.values() if not lem)
    print(f"saved {args.out}: {len(table)} keys, {unknown} without a lemma")
    if args.package:
        rows = sorted(
            f"{k}\t{lem}\n" for k, (lem, _) in table.items() if lem and stem(lem) != stem(k)
        )
        with gzip.open(args.package, "wt", encoding="utf-8", compresslevel=9) as f:
            f.write("".join(rows))
        print(f"saved {args.package}: {len(rows)} words whose stem changes")


if __name__ == "__main__":
    main()
