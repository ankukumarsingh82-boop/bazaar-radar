"""Runtime settings. The API key is read from the environment only, never from source."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from app.boot import note, public_fallbacks

ROOT = Path(__file__).resolve().parent.parent


def default_db_path() -> Path:
    """SQLite path. Vercel’s deployment filesystem is read-only outside /tmp."""
    if os.environ.get("VERCEL"):
        return Path("/tmp/bazaar-radar/bazaar.sqlite")
    return ROOT / "data" / "bazaar.sqlite"


def load_dotenv(path: Path | None = None, bucket: list[str] | None = None) -> None:
    """Load KEY=VALUE lines into the environment without overriding existing vars."""
    env_path = path or ROOT / ".env"
    try:
        if not env_path.exists() or not env_path.is_file():
            return
        text = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        note("env:dotenv", exc, bucket)
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Settings(BaseModel):
    serpapi_api_key: str = ""
    br_mode: str = ""
    daily_cap: int = 40
    max_live_calls_per_report: int = 14
    min_searches_left: int = 20
    fixtures_dir: Path = Field(default_factory=lambda: ROOT / "fixtures")
    db_path: Path = Field(default_factory=default_db_path)
    on_vercel: bool = False
    force_fixtures: bool = False
    startup_fallbacks: list[str] = Field(default_factory=list)

    @property
    def mode(self) -> str:
        if self.force_fixtures:
            return "fixtures"
        if self.br_mode in {"fixtures", "cache", "live"}:
            return self.br_mode
        # A key in the Vercel project must not turn the public demo into live calls.
        if self.on_vercel:
            return "fixtures"
        return "cache" if self.serpapi_api_key else "fixtures"

    @property
    def has_key(self) -> bool:
        return bool(self.serpapi_api_key.strip())


def _int_env(name: str, default: int, code: str, bucket: list[str]) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        note(code, exc, bucket)
        return default


def _db_path(bucket: list[str]) -> Path:
    raw = os.environ.get("BR_DB_PATH", "").strip()
    if not raw:
        try:
            return default_db_path()
        except Exception as exc:  # pragma: no cover - default path is a constant
            note("env:db-path", exc, bucket)
            return Path("/tmp/bazaar-radar/bazaar.sqlite")
    try:
        return Path(raw)
    except (TypeError, ValueError, OSError) as exc:
        note("env:db-path", exc, bucket)
        return Path("/tmp/bazaar-radar/bazaar.sqlite")


def _fixtures_dir(bucket: list[str]) -> Path:
    raw = os.environ.get("BR_FIXTURES_DIR", "").strip()
    if not raw:
        return ROOT / "fixtures"
    try:
        candidate = Path(raw)
        if candidate.is_dir():
            return candidate
    except (TypeError, ValueError, OSError) as exc:
        note("env:fixtures-dir", exc, bucket)
        return ROOT / "fixtures"
    note("env:fixtures-dir", bucket=bucket)
    return ROOT / "fixtures"


def get_settings() -> Settings:
    """Never raises. Broken dashboard env vars become defaults and fixture mode."""
    fallbacks: list[str] = []
    try:
        load_dotenv(bucket=fallbacks)
        daily_cap = _int_env("SERPAPI_DAILY_CAP", 40, "env:daily-cap", fallbacks)
        max_live = _int_env("MAX_LIVE_CALLS_PER_REPORT", 14, "env:max-live-calls", fallbacks)
        min_left = _int_env("MIN_SEARCHES_LEFT", 20, "env:min-searches-left", fallbacks)
        fixtures_dir = _fixtures_dir(fallbacks)
        db_path = _db_path(fallbacks)
        mode = os.environ.get("BR_MODE", "").strip().lower()
        if mode and mode not in {"fixtures", "cache", "live"}:
            note("env:mode", bucket=fallbacks)
            mode = ""
        broken = any(code.startswith("env:") for code in fallbacks)
        if broken and "mode:fixtures" not in fallbacks:
            fallbacks.append("mode:fixtures")
        return Settings(
            serpapi_api_key=os.environ.get("SERPAPI_API_KEY", "").strip(),
            br_mode=mode,
            daily_cap=daily_cap,
            max_live_calls_per_report=max_live,
            min_searches_left=min_left,
            fixtures_dir=fixtures_dir,
            db_path=db_path,
            on_vercel=bool(os.environ.get("VERCEL")),
            force_fixtures=broken,
            startup_fallbacks=public_fallbacks(fallbacks),
        )
    except Exception as exc:
        note("settings:defaults", exc, fallbacks)
        if "mode:fixtures" not in fallbacks:
            fallbacks.append("mode:fixtures")
        return Settings(
            br_mode="fixtures",
            force_fixtures=True,
            on_vercel=bool(os.environ.get("VERCEL")),
            startup_fallbacks=public_fallbacks(fallbacks),
        )
