# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9", "seaborn>=0.13", "pandas>=2.2"]
# ///
"""Draw the README benchmark charts (Uzbek and English) into docs/images/.

Run with: uv run scripts/plot_benchmarks.py  (plotting libraries are not project dependencies).
Numbers come from docs/stage2-experiments.md (6h, 6i, 6j, 6k, 6l, 6m) and eval/results/.
"""

from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"

METRICS = ["R@1", "R@5", "R@10", "MRR"]

# 208 unambiguous LLM questions, full corpus, production search with a reranker (6i, 6j).
RUNS = {
    "uz": [
        "Asl modellar (asl e5-small + asl reranker)",
        "Fine-tune qilingan e5-small + asl reranker",
        "Fine-tune qilingan e5-small + fine-tune qilingan reranker",
    ],
    "en": [
        "Stock models (stock e5-small + stock reranker)",
        "Fine-tuned e5-small + stock reranker",
        "Fine-tuned e5-small + fine-tuned reranker",
    ],
}
RUN_VALUES = [
    [0.394, 0.649, 0.716, 0.502],
    [0.462, 0.764, 0.846, 0.586],
    [0.538, 0.822, 0.875, 0.655],
]

# Independent sets (6k, 6l): strict R@10 and R@10 with judge-confirmed answers.
SETS = {
    "uz": ["GPT-5.4, test qismi\n(104)", '"Ko\'r" savollar\n(120)', "advice.uz, yurist\n(225)"],
    "en": ["GPT-5.4, test half\n(104)", '"Blind" questions\n(120)', "advice.uz, lawyers\n(225)"],
}
SET_STRICT = [0.808, 0.800, 0.876]
SET_JUDGE = [0.856, 0.917, 0.964]

# Search modes on the same 208 questions, full corpus, R@10: eval/results/2026-11-12-*-q1.json
# (stock model) and 2026-11-19-*-rr1-top30.json (production).
MODES = {
    "uz": [
        "Faqat vektor, asl e5-small",
        "Faqat FTS (kalit so'zlar)",
        "Faqat vektor, fine-tune qilingan e5-small",
        "Nizom: gibrid + reranker",
    ],
    "en": [
        "Vector only, stock e5-small",
        "FTS only (keywords)",
        "Vector only, fine-tuned e5-small",
        "Nizom: hybrid + reranker",
    ],
}
MODE_VALUES = [0.370, 0.630, 0.707, 0.875]
MODE_COLORS = ["#4c72b0", "#4c72b0", "#4c72b0", "#55a868"]

# Embedding fine-tune on the 72k-chunk candidate pool, hybrid R@10 without a reranker (6h).
PAIRS = [(0, 0.688), (753, 0.774), (1506, 0.779), (1849, 0.793)]
EPOCHS = [
    (2, 0.793, 7),
    (4, 0.822, 7),
    (4, 0.841, 8),
    (4, 0.808, 9),
    (6, 0.837, 7),
    (6, 0.822, 8),
    (8, 0.827, 7),
    (10, 0.837, 7),
]

TEXT = {
    "uz": {
        "t1": "Fine-tune'dan oldin va keyin (208 ta aniq savol, butun korpus, hakam bilan)",
        "t2": "Mustaqil to'plamlarda R@10",
        "strict": "qat'iy",
        "judge": "hakam bilan",
        "t3": "Qidiruv usullari: R@10 (208 ta aniq savol, butun korpus, hakam bilan)",
        "t4a": "Juftliklar soni (2 epoch)",
        "t4b": "Epoch soni (1 849 juftlik, har nuqta bitta seed)",
        "pairs": "o'qitish juftliklari",
        "epochs": "epoch",
        "pool": "R@10, nomzodlar pool'ida, reranker'siz\nhakam bilan",
    },
    "en": {
        "t1": "Before and after fine-tuning (208 unambiguous questions, full corpus, with judge)",
        "t2": "R@10 on independent sets",
        "strict": "strict",
        "judge": "with judge",
        "t3": "Search methods: R@10 (208 unambiguous questions, full corpus, with judge)",
        "t4a": "Number of pairs (2 epochs)",
        "t4b": "Number of epochs (1,849 pairs, one point per seed)",
        "pairs": "training pairs",
        "epochs": "epochs",
        "pool": "R@10 on the candidate pool, no reranker\nwith judge",
    },
}


def fmt(value: float, lang: str) -> str:
    s = f"{value:.3f}"
    return s.replace(".", ",") if lang == "uz" else s


def comma_ticks(axis, lang: str) -> None:
    """Tick labels with one decimal, using a decimal comma for Uzbek."""
    axis.set_major_formatter(lambda v, _: fmt(v, lang)[:-2])


def label_bars(ax, lang: str) -> None:
    for bars in ax.containers:
        labels = [fmt(b.get_height(), lang) if b.get_height() > 0 else "" for b in bars]
        ax.bar_label(bars, labels=labels, fontsize=8, padding=2)


def chart_finetune(lang: str) -> None:
    rows = [
        {"run": run, "metric": m, "value": v}
        for run, values in zip(RUNS[lang], RUN_VALUES, strict=True)
        for m, v in zip(METRICS, values, strict=True)
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=pd.DataFrame(rows), x="metric", y="value", hue="run", ax=ax)
    label_bars(ax, lang)
    ax.set_ylim(0, 1)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title(TEXT[lang]["t1"])
    comma_ticks(ax.yaxis, lang)
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=1, frameon=False)
    save(fig, f"finetune-{lang}.png")


def chart_independent(lang: str) -> None:
    tx = TEXT[lang]
    rows = []
    for name, strict, judge in zip(SETS[lang], SET_STRICT, SET_JUDGE, strict=True):
        if strict is not None:
            rows.append({"set": name, "kind": tx["strict"], "value": strict})
        rows.append({"set": name, "kind": tx["judge"], "value": judge})
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(
        data=pd.DataFrame(rows),
        x="set",
        y="value",
        hue="kind",
        hue_order=[tx["strict"], tx["judge"]],
        ax=ax,
    )
    label_bars(ax, lang)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("")
    ax.set_ylabel("R@10")
    ax.set_title(tx["t2"])
    comma_ticks(ax.yaxis, lang)
    ax.legend(title="", loc="lower right")
    save(fig, f"independent-{lang}.png")


def chart_modes(lang: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 3.6))
    bars = ax.barh(MODES[lang], MODE_VALUES, color=MODE_COLORS)
    ax.bar_label(bars, labels=[fmt(v, lang) for v in MODE_VALUES], fontsize=9, padding=3)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_title(TEXT[lang]["t3"])
    comma_ticks(ax.xaxis, lang)
    save(fig, f"methods-{lang}.png")


def chart_training(lang: str) -> None:
    tx = TEXT[lang]
    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    x, y = zip(*PAIRS, strict=True)
    left.plot(x, y, marker="o")
    left.set_xticks(x)
    left.set_title(tx["t4a"])
    left.set_xlabel(tx["pairs"])
    left.set_ylabel(tx["pool"])
    epochs = pd.DataFrame(EPOCHS, columns=["epoch", "r10", "seed"])
    right.plot(epochs.groupby("epoch")["r10"].mean(), color="#4c72b0")
    right.scatter(epochs["epoch"], epochs["r10"], color="#4c72b0", zorder=3)
    right.set_xticks(sorted(epochs["epoch"].unique()))
    right.set_title(tx["t4b"])
    right.set_xlabel(tx["epochs"])
    left.set_ylim(0.65, 0.87)
    for ax in (left, right):
        ax.yaxis.set_major_locator(MultipleLocator(0.05))
        ax.yaxis.set_major_formatter(lambda v, _: fmt(v, lang)[:-1])
    save(fig, f"training-{lang}.png")


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print(OUT / name)


if __name__ == "__main__":
    sns.set_theme(style="whitegrid")
    for lang in TEXT:
        chart_finetune(lang)
        chart_independent(lang)
        chart_modes(lang)
        chart_training(lang)
