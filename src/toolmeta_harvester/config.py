import os
from dataclasses import dataclass
from pathlib import Path

from dynaconf import Dynaconf

# Default BASE_DIR for Dynaconf interpolation in config/config.toml.
# BASE_DIR is set to the project root (parent of the config/ directory) when not provided.
os.environ.setdefault("BASE_DIR", str(Path(__file__).resolve().parents[2]))

settings = Dynaconf(
    envvar_prefix="TOOLMETA_HARVESTER",
    settings_files=["config/config.toml", "config/.secrets.toml"],
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
    return os.environ.get("LLM_EGI_API_KEY", settings.get("egi.llm_api_key", ""))


def egi_llm_api_url() -> str:
    return os.environ.get(
        "LLM_EGI_API_URL",
        settings.get("egi.llm_api_url", "https://llm.ai.egi.eu/v1/chat/completions"),
    )


def egi_llm_model() -> str:
    return os.environ.get(
        "LLM_EGI_MODEL",
        settings.get("egi.llm_model", "qwen3.8-27b"),
    )


def egi_llm_stage_model(stage: str) -> str:
    """Resolve a fixed model for one stage, falling back to the run-wide model."""
    if stage not in {"extraction", "generation", "validation"}:
        raise ValueError(f"Unsupported LLM stage: {stage}")
    env_key = f"LLM_EGI_{stage.upper()}_MODEL"
    return os.environ.get(env_key, egi_llm_model())


def embedding_api() -> str:
    egi = settings.egi
    return egi["embedding_api"]


def load_db_config() -> DatabaseConfig:
    db = settings.database
    return DatabaseConfig(
        host=os.environ.get(
            "TOOLMETA_HARVESTER_DATABASE__HOST",
            os.environ.get("POSTGRES_ADDRESS_DOCKER") or db["host"],
        ),
        port=int(
            os.environ.get(
                "TOOLMETA_HARVESTER_DATABASE__PORT",
                os.environ.get("POSTGRES_PORT_DOCKER") or db["port"],
            )
        ),
        user=os.environ.get(
            "TOOLMETA_HARVESTER_DATABASE__USER",
            os.environ.get("POSTGRES_USER") or db["user"],
        ),
        password=os.environ.get(
            "TOOLMETA_HARVESTER_DATABASE__PASSWORD",
            os.environ.get("POSTGRES_PASSWORD") or db["password"],
        ),
        name=os.environ.get("TOOLMETA_HARVESTER_DATABASE__NAME", db["name"]),
    )
