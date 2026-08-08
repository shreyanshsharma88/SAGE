from textual.app import ComposeResult
from textual.widgets import Label, ListItem

from assistant.db.repository import Task

STATUS_MARKERS: dict[str, str] = {"open": "[ ]", "in_progress": "[~]", "done": "[x]"}
PRIORITY_MARKERS: dict[str, str] = {"high": "!!!", "medium": "!!", "low": "!"}


class TaskItem(ListItem):
    def __init__(self, task_data: Task) -> None:
        super().__init__()
        self.task_data: Task = task_data

    def _render_line(self) -> str:
        status_marker: str = STATUS_MARKERS.get(self.task_data.status, "[ ]")
        priority_marker: str = PRIORITY_MARKERS.get(self.task_data.priority, "!!")
        due: str = f"  (due {self.task_data.due_date})" if self.task_data.due_date else ""
        return f"{status_marker} {priority_marker:<3} {self.task_data.title}{due}"

    def compose(self) -> ComposeResult:
        yield Label(self._render_line())
