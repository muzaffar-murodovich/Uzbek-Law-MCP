"""Second-stage reranking with a small multilingual cross-encoder (int8 ONNX, no torch).

The cross-encoder reads the question and one candidate text together and returns a relevance
score. It runs on the first ``top`` units of the fused list only (≈2 s for 20 on two cores).
Its order is blended with the fused order, which was better offline than either alone
(docs/stage2-experiments.md, 6d and 6e).
"""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from qonunshunos.index.embed import ModelSpec, ensure_model
from qonunshunos.text.normalize import embedding_text

RERANKER = ModelSpec(
    name="mmarco-mMiniLMv2-L12-H384-int8",
    repo="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    revision="1427fd652930e4ba29e8149678df786c240d8825",
    files={
        "tokenizer.json": "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
        "onnx/model_quint8_avx2.onnx": (
            "6c2513767fb63d008a4377bef7a7a3555433d9436342bb53e35a3a72ffc52d4b"
        ),
    },
    onnx_file="onnx/model_quint8_avx2.onnx",
)
MAX_TOKENS = 512
DEFAULT_TOP = 20
BLEND = 0.5  # weight of the fused order next to the reranker's order
RANK_K = 10  # reciprocal-rank constant for both orders


class Rerank(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class Reranker:
    def __init__(self, model_dir: Path, threads: int | None = None) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = ensure_model(RERANKER, model_dir)
        self.name = RERANKER.name
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_TOKENS, strategy="longest_first")
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            str(root / RERANKER.onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self.session.get_inputs()}

    def score(self, query: str, texts: Sequence[str], batch_size: int = 8) -> list[float]:
        query = embedding_text(query)
        out: list[float] = []
        for start in range(0, len(texts), batch_size):
            pairs = [(query, embedding_text(t)) for t in texts[start : start + batch_size]]
            encodings = self.tokenizer.encode_batch(pairs)
            width = max(len(e.ids) for e in encodings)
            ids = np.zeros((len(encodings), width), dtype=np.int64)
            mask = np.zeros_like(ids)
            types = np.zeros_like(ids)
            for row, enc in enumerate(encodings):
                ids[row, : len(enc.ids)] = enc.ids
                mask[row, : len(enc.ids)] = 1
                types[row, : len(enc.ids)] = enc.type_ids
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feeds["token_type_ids"] = types
            out.extend(self.session.run(None, feeds)[0][:, 0].tolist())
        return out


def blended_order(scores: Sequence[float], blend: float = BLEND) -> list[int]:
    """Positions 0..n-1 (in fused order) sorted by reranker rank blended with fused rank."""
    by_score = sorted(range(len(scores)), key=lambda i: -scores[i])
    rerank_pos = {i: r for r, i in enumerate(by_score, start=1)}
    return sorted(
        range(len(scores)),
        key=lambda i: -(1 / (RANK_K + rerank_pos[i]) + blend / (RANK_K + i + 1)),
    )


def rerank_top() -> int:
    """How many fused units to rerank: ``QONUNSHUNOS_RERANK_TOP`` (0 turns reranking off)."""
    value = os.environ.get("QONUNSHUNOS_RERANK_TOP", "")
    return int(value) if value.strip().isdigit() else DEFAULT_TOP
