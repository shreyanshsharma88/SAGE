from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListView,
    Static,
    TabbedContent,
    TabPane,
)

from assistant.agent.loop import (
    AgentLoop,
    ChunkEvent,
    DoneEvent,
    ErrorEvent,
    LoopEvent,
    PendingDeleteEvent,
    RefreshEvent,
)
from assistant.db.repository import Category, Knowledge, Repository, Task
from assistant.tui.widgets.note_item import NoteItem
from assistant.tui.widgets.task_item import TaskItem

CATEGORIES: tuple[Category, ...] = ("office", "personal", "side-hustle", "shopping", "learning")
NOTES_PANE_ID: str = "pane_notes"
NOTES_LIST_ID: str = "notes_list"
NOTES_SEARCH_ID: str = "notes-search"
TASK_INPUT_ID: str = "task-input"


def category_to_pane_id(category: Category) -> str:
    return "pane_" + category.replace("-", "_")


def category_to_list_id(category: Category) -> str:
    return "list_" + category.replace("-", "_")


class ConfirmDeleteScreen(ModalScreen[bool]):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task_to_delete: Task = task

    def compose(self) -> ComposeResult:
        with Grid(id="confirm-grid"):
            yield Label(f"Delete task: {self._task_to_delete.title!r}?", id="confirm-question")
            yield Button("Cancel", variant="primary", id="confirm-cancel")
            yield Button("Delete", variant="error", id="confirm-delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-delete")


class TaskListScreen(Screen[None]):
    BINDINGS = [
        Binding("c", "complete_task", "Complete"),
        Binding("d", "delete_task", "Delete"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self._repository: Repository = repository

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            for category in CATEGORIES:
                with TabPane(category, id=category_to_pane_id(category)):
                    yield ListView(id=category_to_list_id(category))
            with TabPane("Notes", id=NOTES_PANE_ID):
                yield Input(placeholder="Search notes…", id=NOTES_SEARCH_ID)
                yield ListView(id=NOTES_LIST_ID)
        yield Static("", id="agent-output")
        yield Input(placeholder="Ask SAGE anything, then press enter", id=TASK_INPUT_ID)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_all()
        self._refresh_notes("")

    def _active_category(self) -> Category:
        tabs: TabbedContent = self.query_one(TabbedContent)
        active_pane_id: str = tabs.active
        for category in CATEGORIES:
            if category_to_pane_id(category) == active_pane_id:
                return category
        return CATEGORIES[0]

    def _refresh_all(self) -> None:
        for category in CATEGORIES:
            self._refresh_category(category)

    def _refresh_category(self, category: Category) -> None:
        list_view: ListView = self.query_one(f"#{category_to_list_id(category)}", ListView)
        list_view.clear()
        for task in self._repository.list_tasks(category=category):
            list_view.append(TaskItem(task))

    def _selected_task_item(self) -> Optional[TaskItem]:
        list_view: ListView = self.query_one(
            f"#{category_to_list_id(self._active_category())}", ListView
        )
        highlighted = list_view.highlighted_child
        if isinstance(highlighted, TaskItem):
            return highlighted
        return None

    def _refresh_notes(self, query: str) -> None:
        list_view: ListView = self.query_one(f"#{NOTES_LIST_ID}", ListView)
        list_view.clear()
        notes: list[Knowledge] = self._notes_for_query(query)
        for note in notes:
            list_view.append(NoteItem(note))

    def _notes_for_query(self, query: str) -> list[Knowledge]:
        tokens: list[str] = [token for token in query.split() if token.isalnum()]
        if not tokens:
            return self._repository.list_knowledge()
        fts_query: str = " ".join(f"{token}*" for token in tokens)
        try:
            return self._repository.search_knowledge(fts_query)
        except Exception:
            return []

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == NOTES_SEARCH_ID:
            self._refresh_notes(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != TASK_INPUT_ID:
            return
        message: str = event.value.strip()
        if not message:
            return
        event.input.value = ""
        self.run_worker(self._run_agent(message), exclusive=True)

    async def _run_agent(self, user_message: str) -> None:
        output: Static = self.query_one("#agent-output", Static)
        output.update("")
        streamed: str = ""
        pending_delete_id: Optional[int] = None
        loop: AgentLoop = AgentLoop(self._repository)
        async for event in loop.run(user_message):
            outcome: LoopEvent = event
            if isinstance(outcome, ChunkEvent):
                streamed += outcome.text
                output.update(streamed)
            elif isinstance(outcome, RefreshEvent):
                self._refresh_all()
            elif isinstance(outcome, PendingDeleteEvent):
                pending_delete_id = outcome.task_id
            elif isinstance(outcome, ErrorEvent):
                output.update(f"[b red]SAGE:[/] {outcome.message}")
                return
            elif isinstance(outcome, DoneEvent):
                if not streamed.strip() and outcome.reply.strip():
                    output.update(outcome.reply)
        if pending_delete_id is not None:
            await self._confirm_agent_delete(pending_delete_id)

    async def _confirm_agent_delete(self, task_id: int) -> None:
        try:
            task: Task = self._repository.get_task(task_id)
        except KeyError:
            return
        confirmed: Optional[bool] = await self.app.push_screen_wait(ConfirmDeleteScreen(task))
        if confirmed:
            self._repository.delete_task(task.id)
            self._refresh_all()

    def action_complete_task(self) -> None:
        item: Optional[TaskItem] = self._selected_task_item()
        if item is None:
            return
        self._repository.complete_task(item.task_data.id)
        self._refresh_category(item.task_data.category)

    def action_delete_task(self) -> None:
        item: Optional[TaskItem] = self._selected_task_item()
        if item is None:
            return
        task: Task = item.task_data

        def _on_confirm(confirmed: Optional[bool]) -> None:
            if confirmed:
                self._repository.delete_task(task.id)
                self._refresh_category(task.category)

        self.app.push_screen(ConfirmDeleteScreen(task), _on_confirm)

    def action_quit_app(self) -> None:
        self.app.exit()
