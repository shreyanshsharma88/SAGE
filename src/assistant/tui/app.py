from textual.app import App

from assistant.db.repository import Repository
from assistant.reminders import REMINDER_POLL_SECONDS, ReminderOutcome, check_and_fire_reminders
from assistant.tui.screens.task_list import TaskListScreen


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
        outcome: ReminderOutcome = check_and_fire_reminders(self.repository)
        if outcome.notify_unavailable:
            self.notify(
                "notify-send not found; reminder popups are unavailable.",
                severity="warning",
            )
