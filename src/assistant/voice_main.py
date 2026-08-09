import asyncio
import sys
from enum import Enum, auto
from typing import Any, AsyncIterator, Callable, Literal, Optional

from assistant.agent.loop import AgentLoop, VoiceTurnResult
from assistant.db.migrations import run_migrations
from assistant.db.repository import Repository
from assistant.voice.audio_stream import SharedAudioStream
from assistant.voice.capture import VadRecorder
from assistant.voice.cues import play_beep
from assistant.voice.stt import WhisperSTT
from assistant.voice.tts import PiperTTS
from assistant.voice.wakeword import WakeWordDetector

Decision = Literal["confirm", "cancel", "unclear"]

CONFIRM_WORDS: set[str] = {"yes", "yeah", "yep", "confirm", "delete", "sure"}
CANCEL_WORDS: set[str] = {"no", "nope", "cancel", "stop", "keep", "dont"}
MAX_CONFIRM_ATTEMPTS: int = 2

RecorderFactory = Callable[[], VadRecorder]
BeepFn = Callable[[], None]


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    SPEAKING = auto()
    CONFIRM_RECORDING = auto()


class VoiceService:
    def __init__(
        self,
        repository: Repository,
        loop: AgentLoop,
        tts: PiperTTS,
        stt: WhisperSTT,
        wake: WakeWordDetector,
        beep: BeepFn,
        recorder_factory: RecorderFactory,
    ) -> None:
        self._repository: Repository = repository
        self._loop: AgentLoop = loop
        self._tts: PiperTTS = tts
        self._stt: WhisperSTT = stt
        self._wake: WakeWordDetector = wake
        self._beep: BeepFn = beep
        self._new_recorder: RecorderFactory = recorder_factory

    def start(self) -> None:
        self._tts.start()

    async def aclose(self) -> None:
        await self._tts.aclose()

    async def _transcribe(self, audio: Any) -> str:
        runtime = asyncio.get_event_loop()
        return await runtime.run_in_executor(None, self._stt.transcribe, audio)

    @staticmethod
    def _classify(answer: str) -> Decision:
        tokens: set[str] = {token.strip(".,!?").lower() for token in answer.split()}
        if tokens & CONFIRM_WORDS:
            return "confirm"
        if tokens & CANCEL_WORDS:
            return "cancel"
        return "unclear"

    def _ask_delete(self, task_id: int) -> bool:
        try:
            task = self._repository.get_task(task_id)
        except KeyError:
            return False
        self._tts.enqueue_sentence(f"Delete the task {task.title}? Say yes or no.")
        return True

    async def run(
        self,
        chunk_source: AsyncIterator[Any],
        enter_event: Optional[asyncio.Event] = None,
    ) -> None:
        state: State = State.IDLE
        recorder: Optional[VadRecorder] = None
        turn_task: Optional[asyncio.Task[VoiceTurnResult]] = None
        cancel: Optional[asyncio.Event] = None
        confirm_task_id: Optional[int] = None
        confirm_attempts: int = 0

        async for chunk in chunk_source:
            triggered: bool = enter_event is not None and enter_event.is_set()
            if enter_event is not None:
                enter_event.clear()

            if state == State.IDLE:
                if triggered or self._wake.detected(chunk):
                    self._beep()
                    self._wake.reset()
                    recorder = self._new_recorder()
                    state = State.RECORDING

            elif state == State.RECORDING:
                assert recorder is not None
                if recorder.feed(chunk):
                    text: str = await self._transcribe(recorder.audio())
                    recorder = None
                    if not text.strip():
                        state = State.IDLE
                    else:
                        cancel = asyncio.Event()
                        turn_task = asyncio.create_task(
                            self._loop.run_voice(text, self._tts, cancel)
                        )
                        state = State.SPEAKING

            elif state == State.SPEAKING:
                assert turn_task is not None and cancel is not None
                if turn_task.done():
                    result: VoiceTurnResult = turn_task.result()
                    turn_task = None
                    cancel = None
                    if result.error is not None:
                        self._tts.enqueue_sentence(result.error)
                        state = State.IDLE
                    elif result.pending_delete_task_id is not None and not result.cancelled:
                        confirm_attempts = 0
                        confirm_task_id = result.pending_delete_task_id
                        if self._ask_delete(confirm_task_id):
                            recorder = self._new_recorder()
                            state = State.CONFIRM_RECORDING
                        else:
                            state = State.IDLE
                    else:
                        state = State.IDLE
                elif triggered or self._wake.detected(chunk):
                    cancel.set()
                    self._tts.stop_and_clear()
                    await turn_task
                    turn_task = None
                    cancel = None
                    self._beep()
                    self._wake.reset()
                    recorder = self._new_recorder()
                    state = State.RECORDING

            elif state == State.CONFIRM_RECORDING:
                assert recorder is not None and confirm_task_id is not None
                if triggered or self._wake.detected(chunk):
                    self._tts.stop_and_clear()
                    self._beep()
                    self._wake.reset()
                    recorder = self._new_recorder()
                    state = State.RECORDING
                elif recorder.feed(chunk):
                    answer: str = await self._transcribe(recorder.audio())
                    recorder = None
                    decision: Decision = self._classify(answer)
                    if decision == "confirm":
                        self._repository.delete_task(confirm_task_id)
                        self._tts.enqueue_sentence("Deleted.")
                        state = State.IDLE
                    elif decision == "cancel":
                        self._tts.enqueue_sentence("Keeping it.")
                        state = State.IDLE
                    else:
                        confirm_attempts += 1
                        if confirm_attempts >= MAX_CONFIRM_ATTEMPTS:
                            self._tts.enqueue_sentence("I wasn't sure, so I kept the task.")
                            state = State.IDLE
                        else:
                            self._ask_delete(confirm_task_id)
                            recorder = self._new_recorder()


async def _read_enter(enter_event: asyncio.Event) -> None:
    runtime = asyncio.get_event_loop()
    while True:
        line: str = await runtime.run_in_executor(None, sys.stdin.readline)
        if line == "":
            return
        enter_event.set()


def build_service() -> VoiceService:
    run_migrations()
    repository: Repository = Repository()
    return VoiceService(
        repository=repository,
        loop=AgentLoop(repository),
        tts=PiperTTS(),
        stt=WhisperSTT(),
        wake=WakeWordDetector(),
        beep=play_beep,
        recorder_factory=VadRecorder,
    )


async def _main_async() -> None:
    service: VoiceService = build_service()
    service.start()
    stream: SharedAudioStream = SharedAudioStream()
    stream.start()
    enter_event: Optional[asyncio.Event] = None
    reader: Optional[asyncio.Task[None]] = None
    if sys.stdin.isatty():
        enter_event = asyncio.Event()
        reader = asyncio.create_task(_read_enter(enter_event))
        print("Wake word active. Say it, or press Enter, to talk. Ctrl-C to quit.")
    else:
        print("Wake word active (headless).")
    try:
        await service.run(stream.chunks(), enter_event)
    finally:
        if reader is not None:
            reader.cancel()
        stream.stop()
        await service.aclose()


def main() -> None:
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
