from dataclasses import dataclass
from typing import Any, Optional

import httpx

from assistant.config import get_config


class SearxngUnreachableError(Exception):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


class SearxngClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url: str = (
            base_url if base_url is not None else get_config().searxng_url
        ).rstrip("/")
        self._timeout: httpx.Timeout = httpx.Timeout(8.0, connect=2.0)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        params: dict[str, str] = {"q": query, "format": "json", "safesearch": "0"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/search", params=params)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError) as exc:
            raise SearxngUnreachableError(
                f"SearxNG isn't reachable at {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise SearxngUnreachableError(
                f"SearxNG returned an error status: {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            raise SearxngUnreachableError(
                "SearxNG did not return JSON; check that the json format is enabled"
            ) from exc

        raw_results: list[dict[str, Any]] = payload.get("results") or []
        results: list[SearchResult] = []
        for entry in raw_results[:limit]:
            url: str = entry.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=entry.get("title") or url,
                    url=url,
                    snippet=entry.get("content") or "",
                    published_date=entry.get("publishedDate"),
                )
            )
        return results
