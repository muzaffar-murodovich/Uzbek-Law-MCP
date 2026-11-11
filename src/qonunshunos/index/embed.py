"""Sentence embeddings with ``multilingual-e5-small`` on onnxruntime (no torch).

Model files are downloaded once from the Hugging Face Hub into ``model_dir`` at a pinned
revision and checked against their sha256.
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
DEFAULT_MODEL = "e5-small-int8"

# Version of the text form fed to the model (see ``embedding_text``). It is part of the name
# stored in documents.meta->>'embed_model', so vectors made from another form are not reused.
TEXT_FORM = "q1"


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
        from tokenizers import Tokenizer

        spec = MODELS[model]
        root = ensure_model(spec, model_dir)
        self.name = embed_name(model)
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_TOKENS)
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
