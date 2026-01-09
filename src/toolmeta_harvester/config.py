from dataclasses import dataclass
from pathlib import Path
import tomllib

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

def load_git_config(path: Path | None = None) -> GitConfig:
    # path = path or Path(__file__).parent / "config/config.toml"
    path = path or Path(__file__).parent.parent.parent / "config/config.toml"

    with path.open("rb") as f:
        data = tomllib.load(f)

    git = data["github"]
    return GitConfig(
        api_key=git["api_key"],
    )

def load_db_config(path: Path | None = None) -> DatabaseConfig:
    # path = path or Path(__file__).parent / "config/config.toml"
    path = path or Path(__file__).parent.parent.parent / "config/config.toml"

    with path.open("rb") as f:
        data = tomllib.load(f)

    db = data["database"]
    return DatabaseConfig(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        name=db["name"],
    )
