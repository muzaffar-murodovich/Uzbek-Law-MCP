"""Compare embedding models offline: vector search over the pool of saved candidate chunks.

    uv run --group bench python scripts/vector_lab.py data/eval/candidates_llm_full.json.gz \
        data/eval/passages_llm_full.json.gz --model intfloat/multilingual-e5-small \
        --model data/models/e5-small-ft1

The pool is every chunk in the passages file (scripts/dump_chunk_texts.py --heading: the
FTS and vector candidates of all questions, ~72k chunks), not the whole corpus. Each model
embeds the pool and the queries (torch, fp32, the live text form) and replaces the saved
vector lists with its own top ``--n-vec``; the FTS lists stay. Printed per model: vector
search alone and the hybrid RRF of the live search (scripts/fusion_lab.py, no reranker).
A ``.onnx`` path is run by the live search's Embedder (onnxruntime), e.g. the int8 file of
scripts/export_onnx.py. The "saved" row uses the stored lists (live int8 model over the
whole corpus) for reference. Pool embeddings are cached in data/eval/vec/.

``--model NAME@VECTORS.npz`` takes the pool vectors from a whole-corpus file of
scripts/embed_file.py (ids, vectors) instead of embedding the pool; NAME embeds the queries.
"""

import argparse
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from fusion_lab import DEFAULT_TAG, Lab, Params
from transformers import AutoModel, AutoTokenizer

from nizom.evaluation import metrics
from nizom.text.normalize import embedding_text

CACHE = Path("data/eval/vec")


DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class Model:
    def __init__(self, name: str, max_len: int) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(name)
        self.model = AutoModel.from_pretrained(name).to(DEVICE).eval()
        self.max_len = max_len

    @torch.inference_mode()
    def embed(self, texts: list[str], prefix: str, batch: int = 0, log: bool = False):
        batch = batch or (256 if DEVICE.type == "cuda" else 32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for n, start in enumerate(range(0, len(order), batch)):
            idx = order[start : start + batch]
            enc = self.tokenizer(
                [prefix + embedding_text(texts[i]) for i in idx],
                padding=True,
                truncation=True,
                max_length=self.max_len,
                return_tensors="pt",
            ).to(DEVICE)
            hidden = self.model(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            out[idx] = F.normalize(pooled, dim=-1).float().cpu().numpy()
            if log and n % 200 == 0:
                print(f"  {start}/{len(texts)}", flush=True)
        return out


class OnnxModel:
    """An ONNX file run by the live search's own Embedder (tokenizer.json next to it)."""

    def __init__(self, name: str, max_len: int) -> None:
        import onnxruntime as ort

        from nizom.index.embed import Embedder, load_tokenizer

        path = Path(name)
        self.embedder = Embedder.__new__(Embedder)  # skip the Hub download of the live model
        self.embedder.tokenizer = load_tokenizer(path.parent / "tokenizer.json", max_len)
        options = ort.SessionOptions()
        # The arena keeps the largest batch's buffers for every shape seen: 5.7 GB on home, OOM.
        options.enable_cpu_mem_arena = False
        self.embedder.session = ort.InferenceSession(
            str(path), options, providers=["CPUExecutionProvider"]
        )
        self.embedder._inputs = {i.name for i in self.embedder.session.get_inputs()}
        self.max_len = max_len

    def embed(self, texts: list[str], prefix: str, batch: int = 3200, log: bool = False):
        if prefix == "query: ":
            return np.stack([self.embedder.query(t) for t in texts])
        parts = []
        for start in range(0, len(texts), batch):
            parts.append(self.embedder.passages(texts[start : start + batch]))
            if log:
                print(f"  {start + len(parts[-1])}/{len(texts)}", flush=True)
        return np.concatenate(parts)


def pool_vectors(model: Model, name: str, ids: list[int], texts: list[str]) -> np.ndarray:
    local = Path(name)
    source = f"{local.resolve()}@{local.stat().st_mtime}" if local.exists() else name
    fingerprint = f"{source}|{model.max_len}|{len(ids)}|{ids[0]}|{ids[-1]}"
    key = hashlib.sha1(fingerprint.encode()).hexdigest()[:12]
    path = CACHE / f"{key}.npy"
    if path.exists():
        return np.load(path)
    print(f"embedding {len(texts)} passages with {name}", flush=True)
    vectors = model.embed(texts, "passage: ", log=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, vectors)
    return vectors


def file_vectors(path: Path, ids: list[int]) -> tuple[np.ndarray, list[int]]:
    """Rows of a scripts/embed_file.py output for the pool ids it has; the ids it lacks."""
    data = np.load(path)
    where = {int(c): n for n, c in enumerate(data["ids"])}
    missing = [c for c in ids if c not in where]
    rows = [where.get(c, 0) for c in ids]
    vectors = data["vectors"][rows].astype(np.float32)
    vectors[[n for n, c in enumerate(ids) if c not in where]] = 0.0  # never retrieved
    return vectors, missing


def row(lab: Lab, label: str, p: Params) -> str:
    m = metrics(lab.ranks(p))
    return (
        f"{m.recall_at_1:>5.3f} {m.recall_at_5:>5.3f} {m.recall_at_10:>6.3f} {m.mrr:>5.3f}  {label}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument("passages", type=Path)
    parser.add_argument("--model", action="append", required=True, help="HF id or local dir")
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--n-vec", type=int, default=50)
    parser.add_argument("--max-len", type=int, default=512)
    args = parser.parse_args()

    lab = Lab(args.candidates, args.tag)
    with gzip.open(args.passages, "rt", encoding="utf-8") as f:
        texts = {int(k): v for k, v in json.load(f).items()}
    ids = sorted(texts)
    missing = {c for c in ids if c not in lab.chunks}
    ids = [c for c in ids if c not in missing]  # every pool chunk needs its unit for scoring
    print(f"{len(lab.questions)} questions ({args.tag}), pool {len(ids)} chunks")

    header = f"{'R@1':>5} {'R@5':>5} {'R@10':>6} {'MRR':>5}  run"
    hybrid, vector_only = Params(), replace(Params(), w_fts=0.0)
    lines = [row(lab, "saved lists: hybrid", hybrid), row(lab, "saved lists: vector", vector_only)]
    saved = [q["vector"] for q in lab.questions]
    for spec in args.model:
        name, _, vector_file = spec.partition("@")
        model = (OnnxModel if name.endswith(".onnx") else Model)(name, args.max_len)
        if vector_file:
            vectors, lacking = file_vectors(Path(vector_file), ids)
            print(f"{vector_file}: {len(lacking)} pool chunks missing", flush=True)
        else:
            vectors = pool_vectors(model, name, ids, [texts[c] for c in ids])
        pool = torch.from_numpy(vectors)
        pool_ids = np.array(ids)
        for q in lab.questions:
            qv = torch.from_numpy(model.embed(q["queries"], "query: "))
            top = (qv @ pool.T).topk(args.n_vec, dim=1).indices.numpy()
            q["vector"] = [pool_ids[row_].tolist() for row_ in top]
        lines += [row(lab, f"{spec}: hybrid", hybrid), row(lab, f"{spec}: vector", vector_only)]
        print(header, *lines, sep="\n", flush=True)
    for q, lists in zip(lab.questions, saved, strict=True):
        q["vector"] = lists


if __name__ == "__main__":
    main()
