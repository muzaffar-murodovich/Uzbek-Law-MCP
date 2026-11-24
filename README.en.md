# Nizom

[O'zbekcha](README.md) | English

A remote MCP server for the legislation of Uzbekistan. An AI assistant (Claude, ChatGPT, Cursor
and others) finds the article that answers a user's question in the current text on
[lex.uz](https://lex.uz), reads it, and links to that exact article in its answer.

- **Endpoint:** `https://nizom.org/mcp` (Streamable HTTP, sign in with Google)
- **Price:** free. 30 searches and 200 other calls per day, 10 per minute.
- **Corpus:** 15,810 acts in force (Uzbek, Latin script): the Constitution, codes, laws,
  presidential decrees and resolutions, Cabinet of Ministers resolutions, ministry orders.
  491,947 chunks, refreshed from lex.uz every night.

## Connecting

| Client | How |
|---|---|
| claude.ai / Claude Desktop | Settings → Connectors → Add custom connector → `https://nizom.org/mcp` |
| ChatGPT | Settings → Apps & Connectors → Advanced settings → Developer mode → new connector |
| Claude Code | `claude mcp add --transport http nizom https://nizom.org/mcp`, then `/mcp` |
| Cursor and others | add the URL as a "remote MCP server (Streamable HTTP)" |

## Tools

| Tool | What it does |
|---|---|
| `search_law` | Hybrid search over the question plus formal rephrasings written by the AI (`alt_queries`); returns the 8 best articles |
| `get_article` | Full text of one article or clause, its status and latest amendments |
| `get_document` | Requisites and table of contents of an act |
| `get_section` | Text of a chapter or section |
| `find_document` | Find an act by name, number or kind |
| `list_codes` | The codes currently in force |

Every result carries a lex.uz link. A search result is about 1,100 tokens; a page never exceeds
about 2,500.

## How search works

```
question + alt_queries ─┬─ FTS (PostgreSQL): normalization → lemma → stemming → IDF weighting ─┐
                        └─ vector: fine-tuned e5-small (ONNX int8) → pgvector HNSW ─────────────┴─ RRF
   → top 30 articles → fine-tuned cross-encoder (reranker) → 8 articles
```

- There is no off-the-shelf stemmer for Uzbek, so we wrote one (case → possessive → plural
  suffixes). It is backed by a lemma table of 9,081 nouns generated with uzmorph.
- The embedding model `multilingual-e5-small` and the reranker `mmarco-mMiniLMv2-L12` were
  fine-tuned on Uzbek legal "question → article" pairs (see below).
- The server has no GPU (one Hetzner box, 2 cores): a search takes 2–3 s, most of it in the reranker.

## Results

Metric: **Recall@10**, the share of questions whose correct article is among the first 10
results. R@1 means the correct article is ranked first. All numbers are measured on the full
corpus, with the production code, on questions rephrased by an AI (`alt_queries`), the way a
real client calls the tool. Full log (in Uzbek): [docs/stage2-experiments.md](docs/stage2-experiments.md).

### Before and after fine-tuning

Set: 208 unambiguous questions written by GPT-5.4 from the whole corpus (`eval/questions_llm_full.yaml`).

| Step | R@1 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|
| Baseline: stock e5-small, no reranker | 0.245 | 0.562 | 0.668 | 0.375 |
| + stock reranker (top 20) | 0.394 | 0.649 | 0.716 | 0.502 |
| Fine-tuned e5-small, no reranker | 0.389 | 0.697 | 0.793 | 0.515 |
| Fine-tuned e5-small + stock reranker | 0.462 | 0.764 | 0.846 | 0.586 |
| **+ lemmas, new fusion, fine-tuned reranker (top 30)** | **0.538** | **0.822** | **0.875** | **0.655** |

End to end: R@10 0.668 → 0.875, and R@1 more than doubled (0.245 → 0.538).

Vector-only search gained the most: R@10 0.25 → 0.66 on the full corpus. On a 72k-chunk
candidate pool the stock model scores 0.385 and the fine-tuned one 0.760.

**Training.** 1,849 "question → article" pairs (written by GPT-5.4, checked against quoted text;
documents used for evaluation were excluded). In-batch negatives, 6 epochs, lr 3e-5. The reranker
was trained on hard negatives mined with the fine-tuned e5 (groups of 1 positive + 15 negatives).
On a rented GPU (RunPod) one training run takes about 40 s and re-embedding the whole corpus
about 5.5 minutes. All GPU experiments together cost about $3.

Observations:
- Going from 753 to 1,849 pairs barely moved the score (0.774 → 0.793). More epochs helped
  (2 epochs 0.793, 6 epochs 0.837, on the pool).
- Seed noise is large: the same settings give R@10 0.808–0.841, so every decision was checked
  across several runs.
- int8 quantization cost nothing (0.837 vs 0.837 on the pool), so the server runs int8.

### Independent checks

The settings above were tuned on those 208 questions, so the number could be optimistic. It was
re-measured on three more sets:

| Set | Questions | R@1 | R@10, strict | R@10, with judge |
|---|---:|---:|---:|---:|
| GPT-5.4 questions, held-out `test` half (never used for tuning) | 104 | 0.529 | 0.856 | — |
| "Blind" questions: written without seeing any article, answers found in the corpus by hand | 120 | 0.408 | 0.800 | 0.917 |
| [advice.uz](https://advice.uz): questions asked by people and answered by lawyers | 225 | 0.493 | 0.876 | 0.964 |

- **Strict** counts only the answers labeled in advance. **With judge** also counts other correct
  articles in the top 10 (found by an LLM judge, each checked against the quoted text). The true
  value lies between the two.
- All three sets tell the same story. On real questions (advice.uz) search does no worse than on
  LLM-written ones.
- On vague questions without context ("How long is a contract signed for?") R@10 is 0.58–0.59.
  There the assistant should ask the user to clarify.

### End-to-end test with Claude Code

Claude Code was given only Nizom (no web search) and 10 questions:

| Criterion | Result |
|---|---|
| Expected article read with `get_article` | 10/10 |
| Links in the answer lead to a real article | 34/35 |
| "Not legal advice" disclaimer | 10/10 |
| Tool calls per question | 3–8 (5 on average) |

## Stack

Python 3.12, [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP),
PostgreSQL 16 + pgvector (halfvec, HNSW), onnxruntime (int8), OAuth 2.1 + Google.
Hosting: a single Hetzner server, systemd + nginx, Cloudflare. Nightly updates, backups and
Telegram alerts. No Docker.

## Development

```sh
uv sync
uv run nizom --help
uv run ruff format . && uv run ruff check . && uv run pytest
```

Tests never touch the network: they use trimmed real pages from `tests/fixtures/`.
Local server: create `.env` from `.env.example`, then `uv run nizom serve --no-auth`.
The fine-tuned model files are not in the repository.

Docs (in Uzbek): [PLAN.md](PLAN.md) (decisions and stages), [docs/](docs/) (design and results of
each stage, research on lex.uz).

## Legal

Official documents (laws, resolutions) are not subject to copyright (Law of Uzbekistan "On
Copyright and Related Rights", [Article 8](https://lex.uz/docs/-1022944#-1023047)). The service is
free and links to lex.uz in every answer. This is an unofficial project, not affiliated with
lex.uz, the "Adolat" National Legal Information Center or any government body. Answers are
general information, not legal advice.

## License

Code: [MIT](LICENSE).
