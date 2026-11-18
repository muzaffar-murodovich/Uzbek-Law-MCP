"""Fine-tune multilingual-e5-small on the pairs of scripts/train_data.py (CUDA if present).

    HF_HUB_DISABLE_XET=1 uv run --group bench python scripts/finetune_e5.py \
        --pairs data/train/pairs.jsonl --out data/models/e5-small-ft1

Each pair gives two anchors for the same passage: the citizen's question and the formal
query. Loss: in-batch negatives (cross-entropy over query-passage cosine similarities, scale
20), as in sentence-transformers' MultipleNegativesRankingLoss. A batch never holds the same
chunk twice, so no positive is used as a negative. Gradient checkpointing keeps memory within
home's 7 GB. Texts go through ``embedding_text`` with
the ``query: `` / ``passage: `` prefixes, exactly as the live search embeds them. The word
embedding matrix (250k tokens, 80 % of the weights) stays frozen: less memory, and a small
training set cannot move rare tokens anyway.
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from qonunshunos.text.normalize import embedding_text

BASE = "intfloat/multilingual-e5-small"


def load_examples(path: Path) -> list[tuple[str, str, int]]:
    """(anchor, passage, chunk id) for the question and the query of every pair."""
    out = []
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        pair = json.loads(line)
        passage = "passage: " + embedding_text(pair["passage"])
        for field in ("question", "query"):
            if pair.get(field):
                out.append(("query: " + embedding_text(pair[field]), passage, pair["chunk_id"]))
    return out


def batches(examples: list, size: int, rng: random.Random) -> list[list]:
    """Shuffled batches with every chunk at most once per batch."""
    pool = examples[:]
    rng.shuffle(pool)
    out: list[list] = []
    while pool:
        batch, seen, rest = [], set(), []
        for ex in pool:
            if len(batch) < size and ex[2] not in seen:
                batch.append(ex)
                seen.add(ex[2])
            else:
                rest.append(ex)
        out.append(batch)
        pool = rest
    return out


DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def encode(model, tokenizer, texts: list[str], max_len: int) -> torch.Tensor:
    enc = tokenizer(texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    enc = enc.to(DEVICE)
    hidden = model(**enc).last_hidden_state
    mask = enc["attention_mask"].unsqueeze(-1).float()
    pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
    return F.normalize(pooled, dim=-1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=Path("data/train/pairs.jsonl"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--scale", type=float, default=20.0)
    parser.add_argument("--max-query", type=int, default=64)
    parser.add_argument("--max-passage", type=int, default=256)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--threads", type=int, default=0, help="torch threads (0: default)")
    args = parser.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    model = AutoModel.from_pretrained(args.base, attn_implementation="sdpa").to(DEVICE)
    model.embeddings.word_embeddings.weight.requires_grad = False
    if DEVICE.type == "cpu":
        # Recompute activations in backward: batch 32 x 256 tokens otherwise needs > 5 GB
        # (OOM on home). A GPU has the memory, so it skips the recomputation.
        model.gradient_checkpointing_enable()
    print(f"device {DEVICE}", flush=True)
    params = [p for p in model.parameters() if p.requires_grad]
    print(f"trainable {sum(p.numel() for p in params) / 1e6:.1f}M "
          f"of {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M", flush=True)  # fmt: skip

    examples = load_examples(args.pairs)
    plan = [batches(examples, args.batch, rng) for _ in range(args.epochs)]
    total = sum(len(p) for p in plan)
    warmup = max(1, total // 10)
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda step: min((step + 1) / warmup, max(0.0, (total - step) / (total - warmup))),
    )
    print(
        f"{len(examples)} examples, {total} steps ({args.epochs} epochs), warmup {warmup}",
        flush=True,
    )

    model.train()
    step, started = 0, time.time()
    for epoch, epoch_batches in enumerate(plan, start=1):
        running = 0.0
        for i, batch in enumerate(epoch_batches, start=1):
            q = encode(model, tokenizer, [b[0] for b in batch], args.max_query)
            p = encode(model, tokenizer, [b[1] for b in batch], args.max_passage)
            logits = args.scale * q @ p.T
            loss = F.cross_entropy(logits, torch.arange(len(batch), device=DEVICE))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            step += 1
            running += loss.item()
            if i % 10 == 0 or i == len(epoch_batches):
                elapsed = time.time() - started
                eta = elapsed / step * (total - step)
                print(f"epoch {epoch} step {i}/{len(epoch_batches)} "
                      f"loss {running / i:.3f} elapsed {elapsed / 60:.1f}m eta {eta / 60:.1f}m",
                      flush=True)  # fmt: skip
        if not math.isfinite(running):
            raise RuntimeError("loss is not finite")

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    meta = {**{k: str(v) for k, v in vars(args).items()}, "examples": len(examples)}
    (args.out / "train_args.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
