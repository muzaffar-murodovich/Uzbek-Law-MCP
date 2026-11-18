"""Embed a chunk-text file (scripts/dump_chunk_texts.py --all --heading) with an ONNX model.

    uv run python scripts/embed_file.py data/embed/chunk_texts_all.json.gz \
        --onnx data/models/gpu1/e6/onnx/model_int8.onnx --out data/embed/e6 --workers 8

For re-embedding the corpus on a rented machine: the passages go through the live search's own
Embedder code (``passage: `` prefix, ``embedding_text``, mean pooling), so the vectors equal
what ``qonunshunos reembed`` would write with the same ONNX file. Work is split into parts of
``--part`` chunks saved as ``<out>/part-NNNNN.npz`` (ids int64, vectors float16); a part that
exists is skipped, so the run can be stopped and started again. ``--merge`` joins the parts
into ``<out>/vectors.npz``. ``--provider cuda`` needs onnxruntime-gpu installed instead of
onnxruntime.
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

    from qonunshunos.index.embed import Embedder, load_tokenizer

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
    if not (args.texts and args.onnx):
        parser.error("texts and --onnx are required")

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

    started, done = time.time(), 0
    init = (str(args.onnx), args.provider, args.threads)
    with Pool(args.workers, initializer=_load, initargs=init) as pool:
        for name, count, seconds in pool.imap_unordered(_embed_part, jobs):
            done += count
            rate = done / (time.time() - started)
            left = sum(len(j[1]) for j in jobs) - done
            print(f"{name}: {count} in {seconds:.0f}s; {done} done, {rate:.0f}/s, "
                  f"eta {left / rate / 60:.0f}m", flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
