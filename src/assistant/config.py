import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_MODEL: str = "phi4-mini"


@dataclass(frozen=True)
class Config:
    model: str
    ollama_url: str
    searxng_url: str
    db_path: Path

    @classmethod
    def load(cls) -> "Config":
        db_path_raw: str = os.environ.get("SAGE_DB_PATH", str(PROJECT_ROOT / "data" / "tasks.db"))
        return cls(
            model=os.environ.get("SAGE_MODEL", DEFAULT_MODEL),
            ollama_url=os.environ.get("SAGE_OLLAMA_URL", "http://localhost:11434"),
            searxng_url=os.environ.get("SAGE_SEARXNG_URL", "http://localhost:8888"),
            db_path=Path(db_path_raw),
        )


def get_config() -> Config:
    return Config.load()
