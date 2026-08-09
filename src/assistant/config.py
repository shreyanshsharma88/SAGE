import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_MODEL: str = "phi4-mini"
DEFAULT_WHISPER_MODEL: str = "base.en"
DEFAULT_PIPER_VOICE: str = "en_US-amy-medium"
SAMPLE_RATE: int = 16000


@dataclass(frozen=True)
class Config:
    model: str
    ollama_url: str
    searxng_url: str
    db_path: Path
    whisper_model: str
    piper_voice_path: Path

    @classmethod
    def load(cls) -> "Config":
        db_path_raw: str = os.environ.get("SAGE_DB_PATH", str(PROJECT_ROOT / "data" / "tasks.db"))
        piper_default: str = str(PROJECT_ROOT / "models" / f"{DEFAULT_PIPER_VOICE}.onnx")
        return cls(
            model=os.environ.get("SAGE_MODEL", DEFAULT_MODEL),
            ollama_url=os.environ.get("SAGE_OLLAMA_URL", "http://localhost:11434"),
            searxng_url=os.environ.get("SAGE_SEARXNG_URL", "http://localhost:8080"),
            db_path=Path(db_path_raw),
            whisper_model=os.environ.get("SAGE_WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
            piper_voice_path=Path(os.environ.get("SAGE_PIPER_VOICE", piper_default)),
        )


def get_config() -> Config:
    return Config.load()
