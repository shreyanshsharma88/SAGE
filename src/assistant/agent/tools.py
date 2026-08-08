from dataclasses import dataclass
from typing import Any, Optional

from assistant.db.repository import Repository, Task

ToolSchema = dict[str, Any]

CATEGORY_VALUES: list[str] = ["office", "personal", "side-hustle", "shopping", "learning"]
PRIORITY_VALUES: list[str] = ["low", "medium", "high"]
STATUS_VALUES: list[str] = ["open", "in_progress", "done"]


@dataclass(frozen=True)
class ToolResult:
    name: str
    content: dict[str, Any]
    refresh: bool = False
    pending_delete_task_id: Optional[int] = None


TOOL_SCHEMAS: list[ToolSchema] = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Create a new task in one of the fixed categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORY_VALUES},
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "priority": {"type": "string", "enum": PRIORITY_VALUES},
                    "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "recurrence_rule": {"type": "string"},
                    "reminder_at": {"type": "string", "description": "ISO datetime"},
                },
                "required": ["category", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks, optionally filtered by category and status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORY_VALUES},
                    "status": {"type": "string", "enum": STATUS_VALUES},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as done by its id.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Request deletion of a task by its id. Deletion requires human confirmation.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_knowledge",
            "description": "Store a knowledge note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_date": {"type": "string"},
                    "tags": {"type": "string"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Full-text search stored knowledge notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
]


def _task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "category": task.category,
        "title": task.title,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date,
    }


def _dispatch_add_task(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    task: Task = repository.add_task(
        category=arguments["category"],
        title=arguments["title"],
        notes=arguments.get("notes"),
        priority=arguments.get("priority", "medium"),
        due_date=arguments.get("due_date"),
        recurrence_rule=arguments.get("recurrence_rule"),
        reminder_at=arguments.get("reminder_at"),
    )
    return ToolResult("add_task", {"created": _task_to_dict(task)}, refresh=True)


def _dispatch_list_tasks(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    tasks: list[Task] = repository.list_tasks(
        category=arguments.get("category"),
        status=arguments.get("status"),
    )
    return ToolResult("list_tasks", {"tasks": [_task_to_dict(task) for task in tasks]})


def _dispatch_complete_task(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    task: Task = repository.complete_task(int(arguments["task_id"]))
    return ToolResult("complete_task", {"completed": _task_to_dict(task)}, refresh=True)


def _dispatch_delete_task(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    task_id: int = int(arguments["task_id"])
    task: Task = repository.get_task(task_id)
    return ToolResult(
        "delete_task",
        {
            "status": "pending_confirmation",
            "task": _task_to_dict(task),
            "note": "Deletion is awaiting explicit human confirmation in the UI.",
        },
        pending_delete_task_id=task_id,
    )


def _dispatch_add_knowledge(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    entry = repository.add_knowledge(
        title=arguments["title"],
        content=arguments["content"],
        source_url=arguments.get("source_url"),
        source_date=arguments.get("source_date"),
        tags=arguments.get("tags"),
    )
    return ToolResult("add_knowledge", {"created_id": entry.id})


def _dispatch_search_knowledge(repository: Repository, arguments: dict[str, Any]) -> ToolResult:
    limit: int = int(arguments.get("limit", 20))
    results = repository.search_knowledge(arguments["query"], limit=limit)
    return ToolResult(
        "search_knowledge",
        {
            "results": [
                {"id": item.id, "title": item.title, "content": item.content}
                for item in results
            ]
        },
    )


def dispatch_tool(repository: Repository, name: str, arguments: dict[str, Any]) -> ToolResult:
    handlers = {
        "add_task": _dispatch_add_task,
        "list_tasks": _dispatch_list_tasks,
        "complete_task": _dispatch_complete_task,
        "delete_task": _dispatch_delete_task,
        "add_knowledge": _dispatch_add_knowledge,
        "search_knowledge": _dispatch_search_knowledge,
    }
    handler = handlers.get(name)
    if handler is None:
        return ToolResult(name, {"error": f"unknown tool: {name}"})
    try:
        return handler(repository, arguments)
    except KeyError as exc:
        return ToolResult(name, {"error": f"missing or unknown argument: {exc}"})
    except Exception as exc:
        return ToolResult(name, {"error": f"{type(exc).__name__}: {exc}"})
