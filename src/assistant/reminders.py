from dataclasses import dataclass, field

from assistant.db.repository import Repository, Task
from assistant.notify import notification_available, send_notification

REMINDER_POLL_SECONDS: float = 60.0


@dataclass(frozen=True)
class ReminderOutcome:
    fired_task_ids: list[int] = field(default_factory=list)
    notify_unavailable: bool = False


def _reminder_body(task: Task) -> str:
    due_label: str = task.due_date or "no due date"
    return f"{task.title} (due {due_label})"


def check_and_fire_reminders(repository: Repository) -> ReminderOutcome:
    due: list[Task] = repository.due_reminders()
    if not due:
        return ReminderOutcome()
    available: bool = notification_available()
    fired: list[int] = []
    for task in due:
        if not repository.claim_reminder(task.id):
            continue
        if available:
            send_notification("SAGE reminder", _reminder_body(task))
            fired.append(task.id)
    return ReminderOutcome(fired_task_ids=fired, notify_unavailable=not available)
