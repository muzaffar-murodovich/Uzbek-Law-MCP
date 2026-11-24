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


def env(name: str, default: str = "") -> str:
    """``NIZOM_<name>``, else the pre-rename ``QONUNSHUNOS_<name>`` (older .env files)."""
    return os.environ.get(f"NIZOM_{name}") or os.environ.get(f"QONUNSHUNOS_{name}", default)


@dataclass(frozen=True)
class Settings:
    dsn: str
    data_dir: Path
    model_dir: Path
    public_url: str = ""  # e.g. https://nizom.org: OAuth issuer and resource
    google_client_id: str = ""
    google_client_secret: str = ""
    dev_login: bool = False  # "test user" sign-in button, only for loopback servers
    contact: str = ""  # e-mail or URL shown on the privacy and terms pages
    telegram_token: str = ""  # operator alerts and the morning report (stage 5)
    telegram_chat_id: str = ""
    backups_dir: Path = Path.home() / "backups"

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "Settings":
        load_dotenv()
        data = data_dir or Path(env("DATA_DIR", "data"))
        return cls(
            dsn=env("DSN", ""),
            data_dir=data,
            model_dir=Path(env("MODEL_DIR", str(data / "models"))),
            public_url=env("PUBLIC_URL", "").rstrip("/"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            dev_login=env("DEV_LOGIN", "") in ("1", "true", "yes"),
            contact=env("CONTACT", ""),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            backups_dir=Path(env("BACKUPS_DIR", str(Path.home() / "backups"))),
        )
