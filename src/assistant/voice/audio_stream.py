import asyncio
import queue
from typing import Any, AsyncIterator, Optional

from assistant.config import SAMPLE_RATE

WAKE_CHUNK_SIZE: int = 512


class SharedAudioStream:
    def __init__(self, sample_rate: int = SAMPLE_RATE, chunk_size: int = WAKE_CHUNK_SIZE) -> None:
        self._sample_rate: int = sample_rate
        self._chunk_size: int = chunk_size
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._stream: Any = None

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        self._queue.put(indata[:, 0].copy())

    def start(self) -> None:
        import sounddevice

        self._stream = sounddevice.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self._chunk_size,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def chunks(self) -> AsyncIterator[Any]:
        runtime = asyncio.get_event_loop()
        while True:
            chunk: Any = await runtime.run_in_executor(None, self._queue.get)
            yield chunk
