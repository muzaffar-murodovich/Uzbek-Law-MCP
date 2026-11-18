"""Write the chunk vectors of scripts/embed_file.py into the database (run it on the server).

    venv/bin/python scripts/load_vectors.py data/embed/vectors.npz

See ``writer.load_vectors``: chunks gone since the text dump are skipped, and a document is
marked with the new model only when all its chunks got a vector; ``qonunshunos reembed`` then
redoes the rest. The HNSW index is dropped first (updating 0.5M indexed rows one by one is
slow) and built again at the end; meanwhile vector search scans the table.
"""

import argparse
import time
from pathlib import Path

import numpy as np

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.index.embed import DEFAULT_MODEL, MODELS, embed_name
from qonunshunos.index.writer import HNSW_INDEX, load_vectors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("vectors", type=Path, help="npz with ids (int64) and vectors (384)")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    parser.add_argument("--batch", type=int, default=20000)
    args = parser.parse_args()

    name = embed_name(args.model)
    data = np.load(args.vectors)
    ids, vectors = data["ids"], data["vectors"]
    if vectors.shape != (len(ids), 384) or not np.isfinite(vectors).all():
        raise SystemExit(f"bad vectors: shape {vectors.shape}")
    started = time.monotonic()

    def progress(line: str) -> None:
        print(f"{time.monotonic() - started:>6.0f}s  {line}", flush=True)

    with connect(Settings.from_env().dsn) as conn:
        conn.execute("DROP INDEX IF EXISTS chunks_embedding")
        progress(f"HNSW index dropped; {len(ids)} vectors to write as {name}")
        result = load_vectors(conn, ids, vectors, name, batch=args.batch, progress=progress)
        progress(
            f"{result.updated} chunks updated, {result.marked} documents marked {name}, "
            f"{result.left} left for `qonunshunos reembed`"
        )
        conn.execute("SET maintenance_work_mem = '512MB'")
        conn.execute(HNSW_INDEX)
        progress("HNSW index built")


if __name__ == "__main__":
    main()
