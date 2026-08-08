import sqlite3
from pathlib import Path
from typing import Callable

from assistant.config import get_config

SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"

MigrationStep = Callable[[sqlite3.Connection], None]


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows: list[tuple[object, ...]] = connection.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    return any(row[1] == column for row in rows)


def _add_reminded_at(connection: sqlite3.Connection) -> None:
    if not _column_exists(connection, "tasks", "reminded_at"):
        connection.execute("ALTER TABLE tasks ADD COLUMN reminded_at TEXT")


MIGRATION_STEPS: list[MigrationStep] = [_add_reminded_at]


def apply_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql: str = SCHEMA_PATH.read_text(encoding="utf-8")
    connection: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        connection.executescript(schema_sql)
        for step in MIGRATION_STEPS:
            step(connection)
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
