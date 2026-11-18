"""Sentence embeddings with ``multilingual-e5-small`` on onnxruntime (no torch).

Model files are downloaded once from the Hugging Face Hub into ``model_dir`` at a pinned
revision and checked against their sha256. A ``local/`` repo (our fine-tuned model, not on the
Hub) is never downloaded: deploy/deploy.sh copies its files into ``model_dir``.
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np

from qonunshunos.text.normalize import embedding_text

log = logging.getLogger(__name__)

DIM = 384
MAX_TOKENS = 512


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    revision: str
    files: dict[str, str]  # path in repo -> sha256
    onnx_file: str


_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
_TOKENIZER = {"tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"}

MODELS = {
    "e5-small-int8": ModelSpec(
        name="e5-small-int8",
        repo="Xenova/multilingual-e5-small",
        revision=_REVISION,
        files={
            **_TOKENIZER,
            "onnx/model_int8.onnx": (
                "4d24e2bc01a447951524466ef533e52944bf48509e6552810bcee1a2711cb02c"
            ),
        },
        onnx_file="onnx/model_int8.onnx",
    ),
    "e5-small-fp32": ModelSpec(
        name="e5-small-fp32",
        repo="Xenova/multilingual-e5-small",
        revision=_REVISION,
        files={
            **_TOKENIZER,
            "onnx/model.onnx": "4aa845c27760e06e9a686b9d8b5d440eae4b6612cd09e5b522b716d3941f77ff",
        },
        onnx_file="onnx/model.onnx",
    ),
}
# e5-small fine-tuned on the question-passage pairs (docs/stage2-experiments.md 6h, 6i), int8 by
# scripts/export_onnx.py. Files: data/models/local__e5-small-e6/2026-11-18 on home.
MODELS["e5-small-e6-int8"] = ModelSpec(
    name="e5-small-e6-int8",
    repo="local/e5-small-e6",
    revision="2026-11-18",
    files={
        "tokenizer.json": "6040ba36e3e2f7b2fa6ae076b69d024a08666bea4c345105a32e542900fcc7e7",
        "onnx/model_int8.onnx": "1e181aa85173f62d05f25e2e1f05a4a57811a45124a8a0bb043aafdf9e068a7d",
    },
    onnx_file="onnx/model_int8.onnx",
)
DEFAULT_MODEL = "e5-small-e6-int8"

# Version of the text form fed to the model (see ``embedding_text``). It is part of the name
# stored in documents.meta->>'embed_model', so vectors made from another form are not reused.
TEXT_FORM = "q1"


def load_tokenizer(path: Path, max_tokens: int = MAX_TOKENS):
    """A tokenizer.json with our own settings: no padding, truncation at ``max_tokens``.

    A file saved by transformers after fine-tuning carries the padding and truncation of its
    last call (BatchLongest, 256). ``encode_batch`` would then pad every text to the batch's
    longest, and ``Embedder._embed`` would count the pad tokens as text: a vector would depend
    on its batch neighbours (cosine 0.5-0.9 to the same text embedded alone).
    """
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path))
    tokenizer.no_padding()
    tokenizer.enable_truncation(max_tokens)
    return tokenizer


def embed_name(model: str) -> str:
    return f"{MODELS[model].name}/{TEXT_FORM}"


class Embed(Protocol):
    def passages(self, texts: Sequence[str]) -> np.ndarray: ...
    def query(self, text: str) -> np.ndarray: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_model(spec: ModelSpec, model_dir: Path) -> Path:
    """Download missing model files; return the local folder of this revision."""
    root = model_dir / spec.repo.replace("/", "__") / spec.revision
    for rel, sha in spec.files.items():
        target = root / rel
        if target.exists() and _sha256(target) == sha:
            continue
        if spec.repo.startswith("local/"):
            raise RuntimeError(
                f"{target} is missing or differs from sha256 {sha[:12]}: {spec.name} is not on "
                "the Hub, copy its files there (deploy/deploy.sh does it from home)"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{spec.repo}/resolve/{spec.revision}/{rel}"
        log.warning("downloading %s", url)
        partial = target.with_suffix(target.suffix + ".part")
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with partial.open("wb") as f:
                for chunk in response.iter_bytes(1 << 20):
                    f.write(chunk)
        if _sha256(partial) != sha:
            partial.unlink()
            raise RuntimeError(f"checksum mismatch for {rel}")
        partial.rename(target)
    return root


class Embedder:
    """e5 embeddings: ``query: `` / ``passage: `` prefixes, mean pooling, L2 normalized."""

    def __init__(
        self, model_dir: Path, model: str = DEFAULT_MODEL, threads: int | None = None
    ) -> None:
        import onnxruntime as ort

        spec = MODELS[model]
        root = ensure_model(spec, model_dir)
        self.name = embed_name(model)
        self.tokenizer = load_tokenizer(root / "tokenizer.json")
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            str(root / spec.onnx_file), options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self.session.get_inputs()}

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch(list(texts))
        width = max(len(e.ids) for e in encodings)
        ids = np.zeros((len(encodings), width), dtype=np.int64)
        mask = np.zeros_like(ids)
        for row, enc in enumerate(encodings):
            ids[row, : len(enc.ids)] = enc.ids
            mask[row, : len(enc.ids)] = 1
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feeds)[0]  # (batch, tokens, dim)
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
        return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)

    def passages(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        # Sort by length so a batch pads to similar sizes; restore order afterwards.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for start in range(0, len(order), batch_size):
            idx = order[start : start + batch_size]
            out[idx] = self._embed([f"passage: {embedding_text(texts[i])}" for i in idx])
        return out

    def query(self, text: str) -> np.ndarray:
        return self._embed([f"query: {embedding_text(text)}"])[0]
