from dataclasses import dataclass
from pathlib import Path
import os

from dynaconf import Dynaconf

# Default BASE_DIR for Dynaconf interpolation in config/config.toml.
# BASE_DIR is set to the project root (parent of the config/ directory) when not provided.
os.environ.setdefault("BASE_DIR", str(Path(__file__).resolve().parents[2]))

settings = Dynaconf(
    envvar_prefix="TOOLMETA_HARVESTER",
    settings_files=[
        str(Path(__file__).resolve().parents[2] / "config/config.toml"),
        str(Path(__file__).resolve().parents[2] / "config/.secrets.toml"),
    ],
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


def load_galaxy_config() -> GitConfig:
    galaxy = settings.galaxy_local
    return GalaxyConfig(api_key=galaxy["api_key"], host_url=galaxy["host_url"])


def load_git_config() -> GitConfig:
    git = settings.github
    return GitConfig(
        api_key=git["api_key"],
    )


def egi_llm_api_key() -> str:
    return str(settings.get("egi.llm_api_key", ""))


def egi_llm_api_url() -> str:
    return str(settings.get("egi.llm_api_url"))


def egi_llm_model() -> str:
    return str(settings.get("egi.llm_model"))


def egi_llm_stage_model(stage: str) -> str:
    """Resolve a fixed model for one stage, falling back to the run-wide model."""
    if stage not in {"extraction", "generation", "validation"}:
        raise ValueError(f"Unsupported LLM stage: {stage}")
    return str(settings.get(f"egi.{stage}_model", egi_llm_model()))


def embedding_api() -> str:
    return str(settings.get("egi.embedding_api"))


def embedding_model() -> str:
    return str(settings.get("egi.embedding_model"))


def llm_timeout() -> int:
    return int(settings.get("egi.llm_timeout", 180))


def llm_retries() -> int:
    return int(settings.get("egi.llm_max_retries", 3))


def load_db_config() -> DatabaseConfig:
    db = settings.database
    return DatabaseConfig(
        host=str(db["host"]),
        port=int(db["port"]),
        user=str(db["user"]),
        password=str(db["password"]),
        name=str(db["name"]),
    )
