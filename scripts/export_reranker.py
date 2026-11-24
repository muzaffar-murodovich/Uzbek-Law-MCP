"""Export a fine-tuned cross-encoder (scripts/finetune_reranker.py) to ONNX and int8.

    uv run --group bench python scripts/export_reranker.py data/models/rr1

Output next to the model: onnx/model.onnx (fp32), onnx/model_int8.onnx (dynamic int8 weights,
per channel) and a tokenizer.json without saved padding. The check scores real-looking pairs
with torch and with both ONNX files, in one padded batch and one pair at a time, the way the
live Reranker (nizom.search.rerank) feeds them.
"""

import argparse
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from tokenizers import Tokenizer
from transformers import AutoModelForSequenceClassification

from nizom.text.normalize import embedding_text

PAIRS = [
    (
        "Ish beruvchi meni ogohlantirmasdan ishdan boʻshatishi mumkinmi?",
        "Ish beruvchi mehnat shartnomasini xodimni kamida ikki oy oldin yozma ravishda "
        "ogohlantirgan holda bekor qilishi mumkin.",
    ),
    ("pensiya yoshi", "Tovarlarning assortimenti shartnomada belgilanadi."),
    (
        "Haydovchilik guvohnomasini qancha muddatga beradi?",
        "Haydovchilik guvohnomasi oʻn yil muddatga beriladi. Guvohnoma muddati tugaganidan "
        "keyin u almashtiriladi, buning uchun tibbiy koʻrikdan oʻtish talab etiladi.",
    ),
]


class Logit(torch.nn.Module):
    def __init__(self, model) -> None:
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, token_type_ids):
        return self.model(
            input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
        ).logits


def feeds(tokenizer: Tokenizer, pairs: list[tuple[str, str]]) -> dict[str, np.ndarray]:
    encodings = tokenizer.encode_batch([(embedding_text(q), embedding_text(t)) for q, t in pairs])
    width = max(len(e.ids) for e in encodings)
    ids = np.zeros((len(pairs), width), dtype=np.int64)
    mask = np.zeros_like(ids)
    types = np.zeros_like(ids)
    for row, enc in enumerate(encodings):
        ids[row, : len(enc.ids)] = enc.ids
        mask[row, : len(enc.ids)] = 1
        types[row, : len(enc.ids)] = enc.type_ids
    return {"input_ids": ids, "attention_mask": mask, "token_type_ids": types}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--opset", type=int, default=18)
    args = parser.parse_args()

    out = args.model / "onnx"
    out.mkdir(exist_ok=True)
    fp32, int8 = out / "model.onnx", out / "model_int8.onnx"
    model = AutoModelForSequenceClassification.from_pretrained(args.model).eval()
    tokenizer = Tokenizer.from_file(str(args.model / "tokenizer.json"))
    tokenizer.no_padding()
    tokenizer.enable_truncation(256, strategy="longest_first")
    example = {k: torch.from_numpy(v) for k, v in feeds(tokenizer, PAIRS[:2]).items()}
    names = ["input_ids", "attention_mask", "token_type_ids"]
    batch_dim, tokens = torch.export.Dim("batch"), torch.export.Dim("tokens", max=512)
    program = torch.onnx.export(
        Logit(model),
        tuple(example[n] for n in names),
        input_names=names,
        output_names=["logits"],
        dynamic_shapes={n: {0: batch_dim, 1: tokens} for n in names},
        opset_version=args.opset,
        dynamo=True,
    )
    program.save(str(fp32), external_data=False)
    # The exporter's value_info for the classifier head trips onnx shape inference in the
    # quantizer ("(384) vs (1)"): quantize a copy without it.
    graph = onnx.load(str(fp32))
    del graph.graph.value_info[:]
    bare = out / "model.bare.onnx"
    onnx.save(graph, str(bare))
    quantize_dynamic(str(bare), str(int8), weight_type=QuantType.QInt8, per_channel=True)
    bare.unlink()
    tokenizer.no_truncation()
    tokenizer.save(str(out / "tokenizer.json"))

    batch = feeds(tokenizer, PAIRS)
    with torch.inference_mode():
        ref = model(**{k: torch.from_numpy(v) for k, v in batch.items()}).logits[:, 0].numpy()
    print("torch", ref.round(3))
    for path in (fp32, int8):
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        together = session.run(None, batch)[0][:, 0]
        alone = np.array([session.run(None, feeds(tokenizer, [p]))[0][0, 0] for p in PAIRS])
        print(f"{path.name}: {path.stat().st_size / 1e6:.0f} MB, batch {together.round(3)}, "
              f"one by one {alone.round(3)}")  # fmt: skip


if __name__ == "__main__":
    main()
