from dataclasses import dataclass
from dynaconf import Dynaconf
import json

settings = Dynaconf(
    envvar_prefix="TOOL_REGISTRY",
    settings_files=["config/config.toml", "config/.secrets.toml"],
)

# Environment variable overrides:
# export TOOL_REGISTRY_DATABASE__HOST=localhost
# export TOOL_REGISTRY_DATABASE__PORT=5432
# export TOOL_REGISTRY_DATABASE__NAME=admin
# export TOOL_REGISTRY_DATABASE__USER=harvester
# export TOOL_REGISTRY_DATABASE__PASSWORD=yoursecretsecret
# export TOOL_REGISTRY_GITHUB__API_KEY=your_github_api_key


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


def load_db_config() -> DatabaseConfig:
    db = settings.database
    return DatabaseConfig(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        name=db["name"],
    )
