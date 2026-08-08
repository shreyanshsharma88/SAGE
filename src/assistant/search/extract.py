from dataclasses import dataclass
from typing import Optional

import httpx
import trafilatura

DEFAULT_TIMEOUT: float = 4.0
DEFAULT_MAX_CHARS: int = 1500
USER_AGENT: str = "sage-assistant/0.1 (+local research tool)"


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    title: str
    text: str
    date: Optional[str] = None


def extract_from_html(url: str, html: str, max_chars: int = DEFAULT_MAX_CHARS) -> Optional[ExtractedPage]:
    text: Optional[str] = trafilatura.extract(
        html, include_comments=False, include_tables=False, no_fallback=False
    )
    if not text:
        return None
    metadata = trafilatura.extract_metadata(html)
    date: Optional[str] = metadata.date if metadata is not None else None
    title: str = metadata.title if metadata is not None and metadata.title else url
    return ExtractedPage(url=url, title=title, text=text[:max_chars], date=date)


async def fetch_and_extract(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Optional[ExtractedPage]:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html: str = response.text
    except httpx.HTTPError:
        return None
    try:
        return extract_from_html(url, html, max_chars)
    except Exception:
        return None
