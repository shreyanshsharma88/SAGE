from textual.app import App

from assistant.db.repository import Repository, Task
from assistant.notify import notification_available, send_notification
from assistant.tui.screens.task_list import TaskListScreen

REMINDER_POLL_SECONDS: float = 60.0


class SageApp(App[None]):
    TITLE = "SAGE"
    SUB_TITLE = "local task manager"
    CSS = """
    #task-input {
        dock: bottom;
        margin: 1 2;
    }

    #agent-output {
        dock: bottom;
        height: auto;
        max-height: 10;
        overflow-y: auto;
        margin: 0 2;
        padding: 0 1;
        color: $text-muted;
    }

    ListView {
        height: 1fr;
    }

    ConfirmDeleteScreen {
        align: center middle;
    }

    #confirm-grid {
        grid-size: 2 2;
        grid-gutter: 1 2;
        padding: 1 2;
        width: 60;
        height: 11;
        border: thick $error 60%;
        background: $surface;
    }

    #confirm-question {
        column-span: 2;
        content-align: center middle;
        width: 100%;
    }

    #confirm-cancel, #confirm-delete {
        width: 100%;
    }
    """

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository: Repository = repository

    def on_mount(self) -> None:
        self.push_screen(TaskListScreen(self.repository))
        self.set_interval(REMINDER_POLL_SECONDS, self.check_reminders)

    def check_reminders(self) -> None:
        due: list[Task] = self.repository.due_reminders()
        if not due:
            return
        available: bool = notification_available()
        warned: bool = False
        for task in due:
            if available:
                due_label: str = task.due_date or "no due date"
                send_notification("SAGE reminder", f"{task.title} (due {due_label})")
            elif not warned:
                self.notify(
                    "notify-send not found; reminder popups are unavailable.",
                    severity="warning",
                )
                warned = True
            self.repository.mark_reminded(task.id)
