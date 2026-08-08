import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from assistant.config import get_config
from assistant.db.migrations import apply_schema

Category = Literal["office", "personal", "side-hustle", "shopping", "learning"]
Priority = Literal["low", "medium", "high"]
Status = Literal["open", "in_progress", "done"]
Role = Literal["user", "assistant", "system", "tool"]


@dataclass(frozen=True)
class Task:
    id: int
    category: Category
    title: str
    notes: Optional[str]
    priority: Priority
    due_date: Optional[str]
    recurrence_rule: Optional[str]
    status: Status
    reminder_at: Optional[str]
    created_at: str
    completed_at: Optional[str]


@dataclass(frozen=True)
class Knowledge:
    id: int
    title: str
    content: str
    source_url: Optional[str]
    source_date: Optional[str]
    tags: Optional[str]
    created_at: str


@dataclass(frozen=True)
class ConversationEntry:
    id: int
    role: Role
    content: str
    created_at: str


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        category=row["category"],
        title=row["title"],
        notes=row["notes"],
        priority=row["priority"],
        due_date=row["due_date"],
        recurrence_rule=row["recurrence_rule"],
        status=row["status"],
        reminder_at=row["reminder_at"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def _knowledge_from_row(row: sqlite3.Row) -> Knowledge:
    return Knowledge(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        source_url=row["source_url"],
        source_date=row["source_date"],
        tags=row["tags"],
        created_at=row["created_at"],
    )


class Repository:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path: Path = db_path if db_path is not None else get_config().db_path
        apply_schema(self._db_path)
        self._connection: sqlite3.Connection = sqlite3.connect(self._db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self._connection.close()

    def add_task(
        self,
        category: Category,
        title: str,
        notes: Optional[str] = None,
        priority: Priority = "medium",
        due_date: Optional[str] = None,
        recurrence_rule: Optional[str] = None,
        reminder_at: Optional[str] = None,
    ) -> Task:
        cursor: sqlite3.Cursor = self._connection.execute(
            "INSERT INTO tasks (category, title, notes, priority, due_date, recurrence_rule, reminder_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (category, title, notes, priority, due_date, recurrence_rule, reminder_at),
        )
        self._connection.commit()
        new_id: int = int(cursor.lastrowid or 0)
        return self.get_task(new_id)

    def get_task(self, task_id: int) -> Task:
        row: Optional[sqlite3.Row] = self._connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        return _task_from_row(row)

    def list_tasks(
        self,
        category: Optional[Category] = None,
        status: Optional[Status] = None,
    ) -> list[Task]:
        clauses: list[str] = []
        params: list[str] = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where: str = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query: str = (
            "SELECT * FROM tasks"
            + where
            + " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
            "COALESCE(due_date, '9999-12-31'), id"
        )
        rows: list[sqlite3.Row] = self._connection.execute(query, params).fetchall()
        return [_task_from_row(row) for row in rows]

    def update_task(
        self,
        task_id: int,
        category: Optional[Category] = None,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date: Optional[str] = None,
        recurrence_rule: Optional[str] = None,
        status: Optional[Status] = None,
        reminder_at: Optional[str] = None,
    ) -> Task:
        fields: dict[str, Optional[str]] = {
            "category": category,
            "title": title,
            "notes": notes,
            "priority": priority,
            "due_date": due_date,
            "recurrence_rule": recurrence_rule,
            "status": status,
            "reminder_at": reminder_at,
        }
        assignments: list[str] = []
        params: list[Optional[str]] = []
        for column, value in fields.items():
            if value is not None:
                assignments.append(f"{column} = ?")
                params.append(value)
        if not assignments:
            return self.get_task(task_id)
        params.append(str(task_id))
        self._connection.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", params
        )
        self._connection.commit()
        return self.get_task(task_id)

    def complete_task(self, task_id: int) -> Task:
        self._connection.execute(
            "UPDATE tasks SET status = 'done', completed_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
        self._connection.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> None:
        self._connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._connection.commit()

    def add_knowledge(
        self,
        title: str,
        content: str,
        source_url: Optional[str] = None,
        source_date: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> Knowledge:
        cursor: sqlite3.Cursor = self._connection.execute(
            "INSERT INTO knowledge (title, content, source_url, source_date, tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, content, source_url, source_date, tags),
        )
        new_id: int = int(cursor.lastrowid or 0)
        self._connection.execute(
            "INSERT INTO knowledge_fts (rowid, title, content) VALUES (?, ?, ?)",
            (new_id, title, content),
        )
        self._connection.commit()
        row: Optional[sqlite3.Row] = self._connection.execute(
            "SELECT * FROM knowledge WHERE id = ?", (new_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"knowledge not found after insert: {new_id}")
        return _knowledge_from_row(row)

    def search_knowledge(self, query: str, limit: int = 20) -> list[Knowledge]:
        rows: list[sqlite3.Row] = self._connection.execute(
            "SELECT knowledge.* FROM knowledge "
            "JOIN knowledge_fts ON knowledge_fts.rowid = knowledge.id "
            "WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [_knowledge_from_row(row) for row in rows]

    def log_conversation(self, role: Role, content: str) -> ConversationEntry:
        cursor: sqlite3.Cursor = self._connection.execute(
            "INSERT INTO conversation_log (role, content) VALUES (?, ?)",
            (role, content),
        )
        self._connection.commit()
        new_id: int = int(cursor.lastrowid or 0)
        row: Optional[sqlite3.Row] = self._connection.execute(
            "SELECT * FROM conversation_log WHERE id = ?", (new_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"conversation entry not found after insert: {new_id}")
        return ConversationEntry(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )

    def recent_conversation(self, limit: int = 20) -> list[ConversationEntry]:
        rows: list[sqlite3.Row] = self._connection.execute(
            "SELECT * FROM conversation_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        entries: list[ConversationEntry] = [
            ConversationEntry(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        entries.reverse()
        return entries
