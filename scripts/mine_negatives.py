"""Mine hard negatives for the training pairs with the live embedding model (GPU if present).

    uv run --group bench python scripts/mine_negatives.py --pairs data/train/pairs.jsonl \
        --vectors data/embed/e6-fp32/vectors.npz --chunks data/embed/chunk_meta.npz \
        --model data/models/gpu1/e6 --out data/train/negatives.jsonl

For the question and the formal query of every pair: the nearest chunks of the whole corpus
(scripts/embed_file.py vectors), without the chunks of the pair's own unit (section), which
may say the same thing. ``--skip`` first hits are left out too, as likely unlabelled answers.
Output: one line per pair and field, ``{"pair": n, "field": "question", "negatives": [ids]}``.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel

from nizom.index.embed import load_tokenizer
from nizom.text.normalize import embedding_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=Path("data/train/pairs.jsonl"))
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True, help="npz: ids, sections")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=30, help="negatives kept per query")
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = np.load(args.vectors)
    ids = data["ids"]
    corpus = torch.from_numpy(data["vectors"].astype(np.float32)).to(device)
    meta = np.load(args.chunks)
    section_of = dict(zip(meta["ids"].tolist(), meta["sections"].tolist(), strict=True))
    sections = np.array([section_of.get(int(c), -1) for c in ids])

    tokenizer = load_tokenizer(args.model / "tokenizer.json")
    model = AutoModel.from_pretrained(args.model).to(device).eval()
    pairs = [json.loads(line) for line in args.pairs.open(encoding="utf-8") if line.strip()]
    jobs = [(n, f, p[f]) for n, p in enumerate(pairs) for f in ("question", "query") if p.get(f)]

    out = args.out.open("w", encoding="utf-8")
    for start in range(0, len(jobs), 128):
        block = jobs[start : start + 128]
        enc = tokenizer.encode_batch([f"query: {embedding_text(t)}" for _n, _f, t in block])
        width = max(len(e.ids) for e in enc)
        tok = torch.zeros((len(enc), width), dtype=torch.long)
        mask = torch.zeros_like(tok)
        for r, e in enumerate(enc):
            tok[r, : len(e.ids)] = torch.tensor(e.ids)
            mask[r, : len(e.ids)] = 1
        tok, mask = tok.to(device), mask.to(device)
        with torch.inference_mode():
            hidden = model(input_ids=tok, attention_mask=mask).last_hidden_state
            w = mask.unsqueeze(-1).float()
            q = F.normalize((hidden * w).sum(1) / w.sum(1), dim=-1)
            top = (q @ corpus.T).topk(args.depth + args.skip + 20, dim=1).indices.cpu().numpy()
        for (n, field, _text), row in zip(block, top, strict=True):
            own = pairs[n]["section_id"]
            found = [int(ids[i]) for i in row if sections[i] != own]
            negatives = found[args.skip : args.skip + args.depth]
            out.write(json.dumps({"pair": n, "field": field, "negatives": negatives}) + "\n")
        print(f"{start + len(block)}/{len(jobs)}", flush=True)
    out.close()


if __name__ == "__main__":
    main()
