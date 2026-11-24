"""Embed a chunk-text file (scripts/dump_chunk_texts.py --all --heading) with an ONNX model.

    uv run python scripts/embed_file.py data/embed/chunk_texts_all.json.gz \
        --onnx data/models/gpu1/e6/onnx/model_int8.onnx --out data/embed/e6 --workers 8

For re-embedding the corpus on a rented machine: the passages go through the live search's own
Embedder code (``passage: `` prefix, ``embedding_text``, mean pooling), so the vectors equal
what ``nizom reembed`` would write with the same ONNX file. Work is split into parts of
``--part`` chunks saved as ``<out>/part-NNNNN.npz`` (ids int64, vectors float16); a part that
exists is skipped, so the run can be stopped and started again. ``--merge`` joins the parts
into ``<out>/vectors.npz``. ``--provider cuda`` needs onnxruntime-gpu installed instead of
onnxruntime. ``--torch DIR`` runs a fine-tuned model folder in fp32 with torch instead (CUDA if
present; ``uv run --group bench``): same text form and pooling, same vectors as its fp32 ONNX.
"""

import argparse
import gzip
import json
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

_embedder = None


def _load(onnx: str, provider: str, threads: int) -> None:
    import onnxruntime as ort

    from nizom.index.embed import Embedder, load_tokenizer

    global _embedder
    path = Path(onnx)
    _embedder = Embedder.__new__(Embedder)  # skip the Hub download of the live model
    _embedder.tokenizer = load_tokenizer(path.parent / "tokenizer.json")
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    # The CPU arena keeps the largest batch's buffers for every shape seen (5.7 GB on home).
    options.enable_cpu_mem_arena = False
    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if provider == "cuda"
        else ["CPUExecutionProvider"]
    )
    _embedder.session = ort.InferenceSession(str(path), options, providers=providers)
    _embedder._inputs = {i.name for i in _embedder.session.get_inputs()}


def _embed_part(job: tuple[Path, list[int], list[str], int]) -> tuple[str, int, float]:
    target, ids, texts, batch = job
    started = time.time()
    vectors = _embedder.passages(texts, batch_size=batch)
    tmp = target.with_suffix(".tmp.npz")
    np.savez(tmp, ids=np.array(ids, dtype=np.int64), vectors=vectors.astype(np.float16))
    tmp.rename(target)
    return target.name, len(ids), time.time() - started


class _TorchEmbedder:
    """Embedder.passages with a transformers model (fp32) in place of onnxruntime."""

    def __init__(self, folder: Path) -> None:
        import torch
        from transformers import AutoModel

        from nizom.index.embed import load_tokenizer

        self.torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = load_tokenizer(folder / "tokenizer.json")
        self.model = AutoModel.from_pretrained(folder).to(self.device).eval()

    def passages(self, texts: list[str], batch_size: int) -> np.ndarray:
        from nizom.text.normalize import embedding_text

        torch = self.torch
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for start in range(0, len(order), batch_size):
            idx = order[start : start + batch_size]
            enc = self.tokenizer.encode_batch([f"passage: {embedding_text(texts[i])}" for i in idx])
            width = max(len(e.ids) for e in enc)
            ids = torch.zeros((len(enc), width), dtype=torch.long)
            mask = torch.zeros_like(ids)
            for r, e in enumerate(enc):
                ids[r, : len(e.ids)] = torch.tensor(e.ids)
                mask[r, : len(e.ids)] = 1
            ids, mask = ids.to(self.device), mask.to(self.device)
            with torch.inference_mode():
                hidden = self.model(input_ids=ids, attention_mask=mask).last_hidden_state
            weights = mask.unsqueeze(-1).float()
            pooled = (hidden * weights).sum(1) / weights.sum(1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, dim=-1)
            out[idx] = pooled.cpu().numpy()
        return out


def merge(out: Path) -> None:
    parts = sorted(out.glob("part-*.npz"))
    ids = np.concatenate([np.load(p)["ids"] for p in parts])
    vectors = np.concatenate([np.load(p)["vectors"] for p in parts])
    if len(np.unique(ids)) != len(ids):
        raise RuntimeError("duplicate chunk ids across parts")
    np.savez(out / "vectors.npz", ids=ids, vectors=vectors)
    print(f"merged {len(parts)} parts: {len(ids)} vectors -> {out / 'vectors.npz'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("texts", type=Path, nargs="?", help="json.gz {chunk id: text}")
    parser.add_argument("--onnx", type=Path)
    parser.add_argument("--torch", type=Path, help="fine-tuned model folder, run in fp32")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--workers", type=int, default=1, help="processes")
    parser.add_argument("--threads", type=int, default=4, help="onnxruntime threads per process")
    parser.add_argument("--part", type=int, default=4096, help="chunks per saved part")
    parser.add_argument("--batch", type=int, default=32, help="texts per model call")
    parser.add_argument("--limit", type=int, help="only the first N chunks (a speed test)")
    parser.add_argument("--merge", action="store_true", help="join the saved parts and stop")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.merge:
        merge(args.out)
        return
    if not args.texts or bool(args.onnx) == bool(args.torch):
        parser.error("texts and one of --onnx / --torch are required")

    with gzip.open(args.texts, "rt", encoding="utf-8") as f:
        texts = {int(k): v for k, v in json.load(f).items()}
    ids = sorted(texts)[: args.limit]
    jobs = []
    for n, start in enumerate(range(0, len(ids), args.part)):
        target = args.out / f"part-{n:05d}.npz"
        if not target.exists():
            part = ids[start : start + args.part]
            jobs.append((target, part, [texts[i] for i in part], args.batch))
    print(f"{len(ids)} chunks, {len(jobs)} parts to do", flush=True)

    started, done, todo = time.time(), 0, sum(len(j[1]) for j in jobs)

    def report(name: str, count: int, seconds: float) -> None:
        nonlocal done
        done += count
        rate = done / (time.time() - started)
        print(f"{name}: {count} in {seconds:.0f}s; {done} done, {rate:.0f}/s, "
              f"eta {(todo - done) / rate / 60:.0f}m", flush=True)  # fmt: skip

    if args.torch:
        global _embedder
        _embedder = _TorchEmbedder(args.torch)
        for job in jobs:
            report(*_embed_part(job))
        return
    init = (str(args.onnx), args.provider, args.threads)
    with Pool(args.workers, initializer=_load, initargs=init) as pool:
        for result in pool.imap_unordered(_embed_part, jobs):
            report(*result)


if __name__ == "__main__":
    main()
