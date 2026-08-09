import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Union

import httpx

from assistant.config import get_config


class OllamaUnreachableError(Exception):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_name: Optional[str] = None


@dataclass(frozen=True)
class ChatChunk:
    text: str


@dataclass(frozen=True)
class ChatCompleted:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False


ChatEvent = Union[ChatChunk, ChatCompleted]


def _message_to_payload(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls is not None:
        payload["tool_calls"] = message.tool_calls
    if message.tool_name is not None:
        payload["tool_name"] = message.tool_name
    return payload


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        config = get_config()
        self._base_url: str = (base_url if base_url is not None else config.ollama_url).rstrip("/")
        self._model: str = model if model is not None else config.model
        self._timeout: httpx.Timeout = httpx.Timeout(120.0, connect=2.0)

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict[str, Any]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[ChatEvent]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_message_to_payload(message) for message in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        cancelled: bool = False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/api/chat", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            cancelled = True
                            break
                        stripped: str = line.strip()
                        if not stripped:
                            continue
                        data: dict[str, Any] = json.loads(stripped)
                        message: dict[str, Any] = data.get("message") or {}
                        piece: str = message.get("content") or ""
                        if piece:
                            content_parts.append(piece)
                            yield ChatChunk(piece)
                        for call in message.get("tool_calls") or []:
                            tool_calls.append(call)
                        if data.get("done"):
                            break
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError) as exc:
            raise OllamaUnreachableError(
                f"Ollama isn't reachable at {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaUnreachableError(
                f"Ollama returned an error status: {exc.response.status_code}"
            ) from exc
        yield ChatCompleted(content="".join(content_parts), tool_calls=tool_calls, cancelled=cancelled)

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
