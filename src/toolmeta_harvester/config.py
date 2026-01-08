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


def load_config(path: Path | None = None) -> DatabaseConfig:
    # path = path or Path(__file__).parent / "config/config.toml"
    path = path or Path(__file__).parent.parent.parent / "config/config-local.toml"

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
