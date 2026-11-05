"""Settings read from the environment (and ``./.env`` if present)."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal ``KEY=value`` reader; existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    dsn: str
    data_dir: Path
    model_dir: Path

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "Settings":
        load_dotenv()
        data = data_dir or Path(os.environ.get("QONUNSHUNOS_DATA_DIR", "data"))
        return cls(
            dsn=os.environ.get("QONUNSHUNOS_DSN", ""),
            data_dir=data,
            model_dir=Path(os.environ.get("QONUNSHUNOS_MODEL_DIR", str(data / "models"))),
        )
