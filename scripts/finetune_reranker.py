"""Fine-tune the cross-encoder reranker on the training pairs with hard negatives (GPU).

    uv run --group bench python scripts/finetune_reranker.py --pairs data/train/pairs.jsonl \
        --negatives data/train/negatives.jsonl --texts data/embed/chunk_texts_all.json.gz \
        --out data/models/rr1

Each training group is one query (the citizen's question or the formal query of a pair), its
passage and ``--group - 1`` negatives sampled from the mined ones (scripts/mine_negatives.py);
the loss is cross-entropy over the group's scores (the passage should win). Texts go through
``embedding_text`` as in the live Reranker; ``--heading`` keeps the chunk heading (document
title and unit) in front of the text, otherwise the reranker reads the text alone, as the
live search gives it today.
"""

import argparse
import gzip
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from nizom.text.normalize import embedding_text

BASE = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def body(text: str, heading: bool) -> str:
    """``heading\\ntext`` (the dump form) → what the reranker reads."""
    return text if heading else text.split("\n", 1)[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=Path("data/train/pairs.jsonl"))
    parser.add_argument("--negatives", type=Path, required=True)
    parser.add_argument("--texts", type=Path, required=True, help="json.gz {id: heading\\ntext}")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--heading", action="store_true")
    parser.add_argument("--group", type=int, default=8, help="passage + negatives per query")
    parser.add_argument("--batch", type=int, default=16, help="groups per step")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with gzip.open(args.texts, "rt", encoding="utf-8") as f:
        texts = {int(k): v for k, v in json.load(f).items()}
    pairs = [json.loads(line) for line in args.pairs.open(encoding="utf-8") if line.strip()]
    mined = [json.loads(line) for line in args.negatives.open(encoding="utf-8") if line.strip()]
    examples = []
    for m in mined:
        pair = pairs[m["pair"]]
        negatives = [c for c in m["negatives"] if c in texts]
        if len(negatives) >= args.group - 1:
            examples.append((pair[m["field"]], body(pair["passage"], args.heading), negatives))
    print(f"{len(examples)} groups of {args.group}, device {device}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForSequenceClassification.from_pretrained(args.base).to(device)
    steps = args.epochs * math.ceil(len(examples) / args.batch)
    warmup = max(1, steps // 10)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min((s + 1) / warmup, max(0.0, (steps - s) / (steps - warmup)))
    )
    model.train()
    step, started = 0, time.time()
    for epoch in range(1, args.epochs + 1):
        rng.shuffle(examples)
        running = 0.0
        for start in range(0, len(examples), args.batch):
            block = examples[start : start + args.batch]
            queries, docs = [], []
            for query, passage, negatives in block:
                group = [passage] + [
                    body(texts[c], args.heading) for c in rng.sample(negatives, args.group - 1)
                ]
                queries += [embedding_text(query)] * len(group)
                docs += [embedding_text(t) for t in group]
            enc = tokenizer(
                queries,
                docs,
                padding=True,
                truncation="longest_first",
                max_length=args.max_length,
                return_tensors="pt",
            ).to(device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(**enc).logits[:, 0].float().view(len(block), args.group)
            loss = F.cross_entropy(logits, torch.zeros(len(block), dtype=torch.long, device=device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            step += 1
            running += loss.item()
            if step % 20 == 0:
                print(f"epoch {epoch} step {step}/{steps} loss {running / 20:.3f} "
                      f"{(time.time() - started) / 60:.1f}m", flush=True)  # fmt: skip
                running = 0.0
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    meta = {k: str(v) for k, v in vars(args).items()} | {"groups": len(examples)}
    (args.out / "train_args.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
