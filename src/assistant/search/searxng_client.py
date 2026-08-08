from dataclasses import dataclass
from typing import Optional

from assistant.config import get_config


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearxngClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url: str = base_url if base_url is not None else get_config().searxng_url

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        assert False, "not yet implemented — next session"
