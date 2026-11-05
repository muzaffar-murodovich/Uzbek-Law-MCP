# Qonunshunos

O'zbekiston Respublikasi qonunchiligiga oid savollarga javob topishda yordam beradigan remote MCP
server (ishchi nom). Manba — [lex.uz](https://lex.uz). Har bir javobda lex.uz'dagi asl hujjatga
havola beriladi.

Reja va qarorlar: [PLAN.md](PLAN.md). Joriy bosqich: [docs/stage1-parser-crawler.md](docs/stage1-parser-crawler.md).

## Ishga tushirish

```sh
uv sync
uv run qonunshunos --help
```

## Ishlab chiqish

```sh
uv run ruff format .
uv run ruff check .
uv run pytest
```

Testlar tarmoqqa chiqmaydi: `tests/fixtures/` dagi qisqartirilgan haqiqiy sahifalar ishlatiladi.
lex.uz'dan yuklangan sahifalar `data/` ga saqlanadi va git'ga qo'shilmaydi.
