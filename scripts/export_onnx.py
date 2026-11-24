"""Export a fine-tuned e5 model (scripts/finetune_e5.py) to ONNX, then quantize it to int8.

    uv run --group bench python scripts/export_onnx.py data/models/e5-small-ft1

The live search reads ONNX on onnxruntime without torch (nizom.index.embed). Output
next to the model: onnx/model.onnx (fp32), onnx/model_int8.onnx (dynamic int8 weights, per
channel) and tokenizer.json. A check embeds a
few real passages with torch and with both ONNX files and prints the cosine between them.
"""

import argparse
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from tokenizers import Tokenizer
from transformers import AutoModel

from nizom.index.embed import load_tokenizer
from nizom.text.normalize import embedding_text

SAMPLES = [
    "query: Ish beruvchi meni ogohlantirmasdan ishdan boʻshatishi mumkinmi?",
    "passage: Mehnat kodeksi. 161-modda. Mehnat shartnomasini ish beruvchining tashabbusiga "
    "koʻra bekor qilish. Ish beruvchi mehnat shartnomasini xodimni kamida ikki oy oldin "
    "yozma ravishda ogohlantirgan holda bekor qilishi mumkin.",
    "query: pensiya yoshi",
    "passage: Fuqarolik kodeksi (ikkinchi qism), 400-modda. Tovarlarning assortimenti",
]


class Hidden(torch.nn.Module):
    """last_hidden_state only: pooling stays outside, as in the live Embedder."""

    def __init__(self, model) -> None:
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, token_type_ids):
        out = self.model(
            input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
        )
        return out.last_hidden_state


def feeds(tokenizer: Tokenizer, texts: list[str]) -> dict[str, np.ndarray]:
    encodings = tokenizer.encode_batch([embedding_text(t) for t in texts])
    width = max(len(e.ids) for e in encodings)
    ids = np.zeros((len(texts), width), dtype=np.int64)
    mask = np.zeros_like(ids)
    for row, enc in enumerate(encodings):
        ids[row, : len(enc.ids)] = enc.ids
        mask[row, : len(enc.ids)] = 1
    return {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}


def pool(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    weights = mask[..., None].astype(np.float32)
    pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path, help="folder saved by finetune_e5.py")
    parser.add_argument("--opset", type=int, default=18)
    args = parser.parse_args()

    out = args.model / "onnx"
    out.mkdir(exist_ok=True)
    fp32, int8 = out / "model.onnx", out / "model_int8.onnx"
    model = AutoModel.from_pretrained(args.model).eval()
    tokenizer = load_tokenizer(args.model / "tokenizer.json")
    example = {k: torch.from_numpy(v) for k, v in feeds(tokenizer, SAMPLES[:2]).items()}
    names = ["input_ids", "attention_mask", "token_type_ids"]
    # The dynamo exporter: the TorchScript one bakes transformers 5's mask code for the example
    # shapes (cosine to torch fell to 0.93 on other batches).
    batch_dim, tokens = torch.export.Dim("batch"), torch.export.Dim("tokens", max=512)
    program = torch.onnx.export(
        Hidden(model),
        tuple(example[n] for n in names),
        input_names=names,
        output_names=["last_hidden_state"],
        dynamic_shapes={n: {0: batch_dim, 1: tokens} for n in names},
        opset_version=args.opset,
        dynamo=True,
    )
    program.save(str(fp32), external_data=False)
    # Per-channel scales: one scale per tensor dropped the fine-tuned model's cosine to torch to
    # 0.93 (the base model's int8 file keeps 0.98); per channel gives 0.98 at the same size.
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8, per_channel=True)
    # Without the padding/truncation transformers saved: onnxruntime users pad themselves.
    tokenizer.no_truncation()
    tokenizer.save(str(out / "tokenizer.json"))

    batch = feeds(tokenizer, SAMPLES)
    with torch.inference_mode():
        hidden = model(**{k: torch.from_numpy(v) for k, v in batch.items()}).last_hidden_state
    reference = pool(hidden.numpy(), batch["attention_mask"])
    for path in (fp32, int8):
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        vectors = pool(session.run(None, batch)[0], batch["attention_mask"])
        cosine = (vectors * reference).sum(axis=1)
        size = path.stat().st_size / 1e6
        print(f"{path.name}: {size:.0f} MB, cosine to torch min {cosine.min():.4f} "
              f"mean {cosine.mean():.4f}")  # fmt: skip


if __name__ == "__main__":
    main()
