"""Second-stage reranking with a small multilingual cross-encoder (int8 ONNX, no torch).

The cross-encoder reads the question and one candidate text together and returns a relevance
score. It runs on the first ``top`` units of the fused list only (≈2 s for 20 on two cores).
Its order is blended with the fused order, which was better offline than either alone
(docs/stage2-experiments.md, 6d and 6e).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from nizom.config import env
from nizom.index.embed import ModelSpec, ensure_model
from nizom.text.normalize import embedding_text

RERANKER_BASE = ModelSpec(
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
# The base model fine-tuned on the question-passage pairs with mined hard negatives
# (scripts/finetune_reranker.py, docs/stage2-experiments.md 6j), int8 by
# scripts/export_reranker.py. Not on the Hub: deploy.sh copies it from home's data/models.
RERANKER = ModelSpec(
    name="mmarco-uz-rr1-int8",
    repo="local/mmarco-uz-rr1",
    revision="2026-11-19",
    files={
        "tokenizer.json": "3a56def25aa40facc030ea8b0b87f3688e4b3c39eb8b45d5702b3a1300fe2a20",
        "onnx/model_int8.onnx": (
            "628a5442ef35a188fe3552ce5a39f0d7c5898dec9ee94ccf0e08ef1125481693"
        ),
    },
    onnx_file="onnx/model_int8.onnx",
)
MAX_TOKENS = 256  # same quality as 512 offline (6e), a third faster
DEFAULT_TOP = 30
BLEND = 0.5  # weight of the fused order next to the reranker's order
RANK_K = 10  # reciprocal-rank constant for both orders


class Rerank(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class Reranker:
    def __init__(
        self, model_dir: Path, threads: int | None = None, max_tokens: int = MAX_TOKENS
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = ensure_model(RERANKER, model_dir)
        self.name = RERANKER.name
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.no_padding()  # padding is done below, per batch
        self.tokenizer.enable_truncation(max_tokens, strategy="longest_first")
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            str(root / RERANKER.onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self.session.get_inputs()}

    def score(self, query: str, texts: Sequence[str], batch_size: int = 4) -> list[float]:
        """One score per text, in the given order. Texts are scored in length order, so a
        batch pads little (a third faster for 30 texts on the server)."""
        query = embedding_text(query)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        scores = [0.0] * len(texts)
        for start in range(0, len(order), batch_size):
            part = order[start : start + batch_size]
            for i, value in zip(part, self._score(query, [texts[i] for i in part]), strict=True):
                scores[i] = value
        return scores

    def _score(self, query: str, texts: Sequence[str]) -> list[float]:
        encodings = self.tokenizer.encode_batch([(query, embedding_text(t)) for t in texts])
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
        return self.session.run(None, feeds)[0][:, 0].tolist()


def blended_order(scores: Sequence[float], blend: float = BLEND) -> list[int]:
    """Positions 0..n-1 (in fused order) sorted by reranker rank blended with fused rank."""
    by_score = sorted(range(len(scores)), key=lambda i: -scores[i])
    rerank_pos = {i: r for r, i in enumerate(by_score, start=1)}
    return sorted(
        range(len(scores)),
        key=lambda i: -(1 / (RANK_K + rerank_pos[i]) + blend / (RANK_K + i + 1)),
    )


def rerank_top() -> int:
    """How many fused units to rerank: ``NIZOM_RERANK_TOP`` (0 turns reranking off)."""
    value = env("RERANK_TOP")
    return int(value) if value.strip().isdigit() else DEFAULT_TOP
