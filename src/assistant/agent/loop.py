import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Optional, Protocol, Union

from assistant.agent.ollama_client import (
    ChatChunk,
    ChatCompleted,
    ChatMessage,
    OllamaClient,
    OllamaUnreachableError,
)
from assistant.agent.tools import (
    TOOL_SCHEMAS,
    WEB_SEARCH_TOOL_NAME,
    ToolResult,
    dispatch_tool,
    dispatch_web_search,
)
from assistant.db.repository import ConversationEntry, Repository
from assistant.search.searxng_client import SearxngUnreachableError

SYSTEM_PROMPT: str = (
    "You are SAGE, a local task assistant. Use the provided tools to manage the user's tasks "
    "and knowledge. Categories are office, personal, side-hustle, shopping, learning. Priorities "
    "are low, medium, high. Dates use ISO format YYYY-MM-DD. Keep replies short and concrete. "
    "To delete a task, call delete_task; deletion is confirmed by the user, never assume it happened. "
    "For anything current or time-sensitive, call web_search and answer only from the fetched "
    "sources, never from your own training knowledge. If the user asks you to remember or note "
    "what you find, follow the web_search with an add_knowledge call summarizing the key points "
    "and their source URLs."
)

WEB_SEARCH_INSTRUCTION: str = (
    "Answer using only the web_search sources above. Attribute every specific claim to a source "
    "URL and its date, and if a source has no date say the date is unknown for it. If two sources "
    "disagree, say so instead of silently choosing one. Clearly label anything you infer or that "
    "the fetched text does not directly support as speculation, not fact. If the sources do not "
    "actually answer the question, say so plainly rather than filling the gap from memory."
)


@dataclass(frozen=True)
class ChunkEvent:
    text: str


@dataclass(frozen=True)
class RefreshEvent:
    pass


@dataclass(frozen=True)
class PendingDeleteEvent:
    task_id: int


@dataclass(frozen=True)
class DoneEvent:
    reply: str


@dataclass(frozen=True)
class ErrorEvent:
    message: str


LoopEvent = Union[ChunkEvent, RefreshEvent, PendingDeleteEvent, DoneEvent, ErrorEvent]

SENTENCE_BOUNDARIES: str = ".!?\n"


class SentenceSink(Protocol):
    def enqueue_sentence(self, text: str) -> None: ...


class SentenceBuffer:
    def __init__(self) -> None:
        self._buffer: str = ""

    def add(self, text: str) -> list[str]:
        self._buffer += text
        sentences: list[str] = []
        while True:
            boundary: Optional[int] = self._first_boundary(self._buffer)
            if boundary is None:
                break
            sentence: str = self._buffer[: boundary + 1].strip()
            self._buffer = self._buffer[boundary + 1 :]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self) -> Optional[str]:
        remaining: str = self._buffer.strip()
        self._buffer = ""
        return remaining or None

    @staticmethod
    def _first_boundary(text: str) -> Optional[int]:
        positions: list[int] = [text.find(char) for char in SENTENCE_BOUNDARIES]
        found: list[int] = [position for position in positions if position >= 0]
        return min(found) if found else None


@dataclass(frozen=True)
class VoiceTurnResult:
    reply: str
    pending_delete_task_id: Optional[int]
    cancelled: bool
    error: Optional[str]


class AgentLoop:
    def __init__(
        self,
        repository: Repository,
        client: Optional[OllamaClient] = None,
        history_turns: int = 10,
    ) -> None:
        self._repository: Repository = repository
        self._client: OllamaClient = client if client is not None else OllamaClient()
        self._history_turns: int = history_turns

    def _load_history(self) -> list[ChatMessage]:
        entries: list[ConversationEntry] = self._repository.recent_conversation(
            limit=self._history_turns * 2
        )
        return [
            ChatMessage(role=entry.role, content=entry.content)
            for entry in entries
            if entry.role in ("user", "assistant")
        ]

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            parsed: Any = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        return {}

    async def _pump(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict[str, Any]]],
        holder: list[ChatCompleted],
    ) -> AsyncIterator[LoopEvent]:
        async for event in self._client.chat(messages, tools=tools):
            if isinstance(event, ChatChunk):
                yield ChunkEvent(event.text)
            elif isinstance(event, ChatCompleted):
                holder.append(event)

    async def run(self, user_message: str) -> AsyncIterator[LoopEvent]:
        self._repository.log_conversation("user", user_message)
        messages: list[ChatMessage] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        messages.extend(self._load_history())
        messages.append(ChatMessage(role="user", content=user_message))

        first_holder: list[ChatCompleted] = []
        try:
            async for event in self._pump(messages, TOOL_SCHEMAS, first_holder):
                yield event
        except OllamaUnreachableError as exc:
            yield ErrorEvent(str(exc))
            return

        first: ChatCompleted = first_holder[-1] if first_holder else ChatCompleted("", [])

        if not first.tool_calls:
            reply: str = first.content
            self._repository.log_conversation("assistant", reply)
            yield DoneEvent(reply)
            return

        messages.append(
            ChatMessage(role="assistant", content=first.content, tool_calls=first.tool_calls)
        )
        for call in first.tool_calls:
            function: dict[str, Any] = call.get("function") or {}
            name: str = function.get("name", "")
            try:
                arguments: dict[str, Any] = self._parse_arguments(function.get("arguments"))
            except json.JSONDecodeError:
                yield ErrorEvent(f"The model sent invalid arguments for {name!r}.")
                return
            if name == WEB_SEARCH_TOOL_NAME:
                try:
                    result: ToolResult = await dispatch_web_search(
                        arguments.get("query", ""),
                        int(arguments.get("max_results", 4)),
                    )
                except SearxngUnreachableError:
                    yield ErrorEvent("Web search isn't available right now.")
                    return
            else:
                result = dispatch_tool(self._repository, name, arguments)
            if result.refresh:
                yield RefreshEvent()
            if result.pending_delete_task_id is not None:
                yield PendingDeleteEvent(result.pending_delete_task_id)
            messages.append(
                ChatMessage(
                    role="tool",
                    content=json.dumps(result.content),
                    tool_name=result.name,
                )
            )
            if name == WEB_SEARCH_TOOL_NAME:
                messages.append(ChatMessage(role="system", content=WEB_SEARCH_INSTRUCTION))

        final_holder: list[ChatCompleted] = []
        try:
            async for event in self._pump(messages, None, final_holder):
                yield event
        except OllamaUnreachableError as exc:
            yield ErrorEvent(str(exc))
            return

        final_reply: str = final_holder[-1].content if final_holder else ""
        self._repository.log_conversation("assistant", final_reply)
        yield DoneEvent(final_reply)

    async def _pump_voice(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict[str, Any]]],
        cancel_event: asyncio.Event,
        emit: Callable[[str], None],
    ) -> ChatCompleted:
        completed: Optional[ChatCompleted] = None
        async for event in self._client.chat(messages, tools=tools, cancel_event=cancel_event):
            if isinstance(event, ChatChunk):
                emit(event.text)
            elif isinstance(event, ChatCompleted):
                completed = event
        return completed if completed is not None else ChatCompleted("", [], False)

    async def _dispatch_calls_voice(
        self,
        messages: list[ChatMessage],
        tool_calls: list[dict[str, Any]],
    ) -> tuple[Optional[int], Optional[str]]:
        pending_delete: Optional[int] = None
        for call in tool_calls:
            function: dict[str, Any] = call.get("function") or {}
            name: str = function.get("name", "")
            try:
                arguments: dict[str, Any] = self._parse_arguments(function.get("arguments"))
            except json.JSONDecodeError:
                return pending_delete, f"The model sent invalid arguments for {name!r}."
            if name == WEB_SEARCH_TOOL_NAME:
                try:
                    result: ToolResult = await dispatch_web_search(
                        arguments.get("query", ""),
                        int(arguments.get("max_results", 4)),
                    )
                except SearxngUnreachableError:
                    return pending_delete, "Web search isn't available right now."
            else:
                result = dispatch_tool(self._repository, name, arguments)
            if result.pending_delete_task_id is not None:
                pending_delete = result.pending_delete_task_id
            messages.append(
                ChatMessage(role="tool", content=json.dumps(result.content), tool_name=result.name)
            )
            if name == WEB_SEARCH_TOOL_NAME:
                messages.append(ChatMessage(role="system", content=WEB_SEARCH_INSTRUCTION))
        return pending_delete, None

    async def run_voice(
        self,
        user_message: str,
        tts: SentenceSink,
        cancel_event: asyncio.Event,
    ) -> VoiceTurnResult:
        self._repository.log_conversation("user", user_message)
        messages: list[ChatMessage] = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        messages.extend(self._load_history())
        messages.append(ChatMessage(role="user", content=user_message))

        buffer: SentenceBuffer = SentenceBuffer()
        spoken: list[str] = []

        def emit(text: str) -> None:
            spoken.append(text)
            for sentence in buffer.add(text):
                tts.enqueue_sentence(sentence)

        try:
            first: ChatCompleted = await self._pump_voice(messages, TOOL_SCHEMAS, cancel_event, emit)
        except OllamaUnreachableError as exc:
            return VoiceTurnResult("".join(spoken), None, False, str(exc))

        if first.cancelled:
            reply: str = "".join(spoken)
            self._repository.log_conversation("assistant", reply)
            return VoiceTurnResult(reply, None, True, None)

        if not first.tool_calls:
            tail: Optional[str] = buffer.flush()
            if tail is not None:
                tts.enqueue_sentence(tail)
            reply = "".join(spoken)
            self._repository.log_conversation("assistant", reply)
            return VoiceTurnResult(reply, None, False, None)

        messages.append(
            ChatMessage(role="assistant", content=first.content, tool_calls=first.tool_calls)
        )
        pending_delete, error = await self._dispatch_calls_voice(messages, first.tool_calls)
        if error is not None:
            return VoiceTurnResult("".join(spoken), pending_delete, False, error)

        second_buffer: SentenceBuffer = SentenceBuffer()
        second_spoken: list[str] = []

        def emit_second(text: str) -> None:
            second_spoken.append(text)
            for sentence in second_buffer.add(text):
                tts.enqueue_sentence(sentence)

        try:
            second: ChatCompleted = await self._pump_voice(messages, None, cancel_event, emit_second)
        except OllamaUnreachableError as exc:
            return VoiceTurnResult("".join(second_spoken), pending_delete, False, str(exc))

        if not second.cancelled:
            tail = second_buffer.flush()
            if tail is not None:
                tts.enqueue_sentence(tail)

        reply = "".join(second_spoken)
        self._repository.log_conversation("assistant", reply)
        return VoiceTurnResult(reply, pending_delete, second.cancelled, None)
