from dataclasses import dataclass
import os
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


def egi_token() -> str:
    egi = settings.egi
    return egi["token"]


def load_db_config() -> DatabaseConfig:
    db = settings.database
    return DatabaseConfig(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        name=db["name"],
    )
