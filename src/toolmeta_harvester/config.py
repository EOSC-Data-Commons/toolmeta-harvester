from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dynaconf import Dynaconf  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
settings = Dynaconf(
    envvar_prefix="TOOLMETA_HARVESTER",
    settings_files=[
        str(PROJECT_ROOT / "config/config.toml"),
        str(PROJECT_ROOT / "config/.secrets.toml"),
    ],
    load_dotenv=True,
    dotenv_path=str(PROJECT_ROOT / ".env"),
    environments=False,
)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    name: str


@dataclass(frozen=True)
class GitConfig:
    api_key: str


@dataclass(frozen=True)
class GalaxyConfig:
    api_key: str
    host_url: str


def load_galaxy_config() -> GalaxyConfig:
    galaxy = settings.galaxy_local
    return GalaxyConfig(api_key=galaxy["api_key"], host_url=galaxy["host_url"])


def load_git_config() -> GitConfig:
    return GitConfig(api_key=str(settings.get("github.api_key", "")))


def _required(path: str) -> str:
    value = settings.get(path)
    if (
        value is None
        or not str(value).strip()
        or str(value).casefold().startswith("your_")
    ):
        raise ValueError(f"Required configuration {path!r} is missing")
    return str(value)


def egi_llm_api_key() -> str:
    return _required("egi.llm_api_key")


def egi_llm_api_url() -> str:
    return str(settings.get("egi.llm_api_url"))


def egi_llm_model() -> str:
    return str(settings.get("egi.generation_model"))


def egi_llm_stage_model(stage: str) -> str:
    if stage not in {"generation", "validation"}:
        raise ValueError(f"Unsupported LLM stage: {stage}")
    return str(settings.get(f"egi.{stage}_model"))


def embedding_api() -> str:
    return str(settings.get("egi.embedding_api"))


def embedding_model() -> str:
    return str(settings.get("egi.embedding_model"))


def llm_timeout() -> int:
    return int(settings.get("egi.llm_timeout"))


def llm_retries() -> int:
    return int(settings.get("egi.llm_max_retries"))


def load_db_config() -> DatabaseConfig:
    db = settings.database
    password = str(db.get("password", ""))
    if not password or password.casefold().startswith(("your_", "replace_")):
        raise ValueError("Required configuration 'database.password' is missing")
    return DatabaseConfig(
        host=str(db["host"]),
        port=int(db["port"]),
        user=str(db["user"]),
        password=password,
        name=str(db["name"]),
    )
