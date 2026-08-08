from textual.app import ComposeResult
from textual.widgets import Label, ListItem

from assistant.db.repository import Knowledge

SNIPPET_LENGTH: int = 120


class NoteItem(ListItem):
    def __init__(self, note_data: Knowledge) -> None:
        super().__init__()
        self.note_data: Knowledge = note_data

    def _render_line(self) -> str:
        note: Knowledge = self.note_data
        date_part: str = note.source_date or note.created_at
        source: str = f"  <{note.source_url}>" if note.source_url else ""
        snippet: str = note.content.replace("\n", " ")[:SNIPPET_LENGTH]
        return f"[b]{note.title}[/b]  ({date_part}){source}\n    {snippet}"

    def compose(self) -> ComposeResult:
        yield Label(self._render_line(), markup=True)
