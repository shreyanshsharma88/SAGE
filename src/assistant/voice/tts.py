import asyncio
from pathlib import Path
from typing import Any, Callable, Optional

from assistant.config import get_config

Synthesizer = Callable[[str], "tuple[Any, int]"]


class AudioPlayer:
    def play(self, samples: Any, sample_rate: int) -> None:
        import sounddevice

        sounddevice.play(samples, sample_rate)
        sounddevice.wait()

    def stop(self) -> None:
        import sounddevice

        sounddevice.stop()


class PiperTTS:
    def __init__(
        self,
        voice_path: Optional[Path] = None,
        synthesizer: Optional[Synthesizer] = None,
        player: Optional[AudioPlayer] = None,
    ) -> None:
        self._voice_path: Path = voice_path if voice_path is not None else get_config().piper_voice_path
        self._synthesizer: Optional[Synthesizer] = synthesizer
        self._player: AudioPlayer = player if player is not None else AudioPlayer()
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._generation: int = 0
        self._worker: Optional[asyncio.Task[None]] = None
        self._voice: Any = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    def enqueue_sentence(self, text: str) -> None:
        stripped: str = text.strip()
        if stripped:
            self._queue.put_nowait(stripped)

    def stop_and_clear(self) -> None:
        self._generation += 1
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._player.stop()

    async def aclose(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        self._player.stop()

    async def _run(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            text: str = await self._queue.get()
            generation: int = self._generation
            try:
                samples, sample_rate = await loop.run_in_executor(None, self._synthesize, text)
                if generation != self._generation:
                    continue
                await loop.run_in_executor(None, self._player.play, samples, sample_rate)
            finally:
                self._queue.task_done()

    def _synthesize(self, text: str) -> "tuple[Any, int]":
        if self._synthesizer is not None:
            return self._synthesizer(text)
        import numpy

        voice = self._ensure_voice()
        chunks: list[Any] = [
            numpy.frombuffer(raw, dtype=numpy.int16)
            for raw in voice.synthesize_stream_raw(text)
        ]
        if chunks:
            samples = numpy.concatenate(chunks)
        else:
            samples = numpy.zeros(0, dtype=numpy.int16)
        return samples, int(voice.config.sample_rate)

    def _ensure_voice(self) -> Any:
        if self._voice is None:
            from piper import PiperVoice

            self._voice = PiperVoice.load(str(self._voice_path))
        return self._voice
