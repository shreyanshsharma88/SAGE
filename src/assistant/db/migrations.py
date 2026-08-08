import sqlite3
from pathlib import Path

from assistant.config import get_config

SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"


def apply_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql: str = SCHEMA_PATH.read_text(encoding="utf-8")
    connection: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        connection.executescript(schema_sql)
        connection.commit()
    finally:
        connection.close()


def run_migrations() -> Path:
    db_path: Path = get_config().db_path
    apply_schema(db_path)
    return db_path


if __name__ == "__main__":
    created_path: Path = run_migrations()
    print(f"migrations applied: {created_path}")
