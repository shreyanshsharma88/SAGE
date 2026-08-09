from typing import Any, Callable, Optional

from assistant.config import SAMPLE_RATE

VAD_BLOCK_SIZE: int = 512
SPEECH_THRESHOLD: float = 0.5
DEFAULT_MAX_SECONDS: float = 18.0
DEFAULT_SILENCE_SECONDS: float = 1.2

VadProbability = Callable[[Any, int], float]

_vad_model: Any = None


def _load_vad() -> Any:
    global _vad_model
    if _vad_model is None:
        import torch

        model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        _vad_model = model
    return _vad_model


def _default_probability(chunk: Any, sample_rate: int) -> float:
    import torch

    vad = _load_vad()
    return float(vad(torch.from_numpy(chunk), sample_rate).item())


class VadRecorder:
    def __init__(
        self,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        silence_seconds: float = DEFAULT_SILENCE_SECONDS,
        sample_rate: int = SAMPLE_RATE,
        probability: Optional[VadProbability] = None,
    ) -> None:
        self._max_seconds: float = max_seconds
        self._silence_seconds: float = silence_seconds
        self._sample_rate: int = sample_rate
        self._probability: VadProbability = probability if probability is not None else _default_probability
        self._frames: list[Any] = []
        self._speech_started: bool = False
        self._silence_run: float = 0.0
        self._elapsed: float = 0.0

    def feed(self, chunk: Any) -> bool:
        self._frames.append(chunk)
        duration: float = len(chunk) / self._sample_rate
        self._elapsed += duration
        if self._probability(chunk, self._sample_rate) >= SPEECH_THRESHOLD:
            self._speech_started = True
            self._silence_run = 0.0
        elif self._speech_started:
            self._silence_run += duration
            if self._silence_run >= self._silence_seconds:
                return True
        return self._elapsed >= self._max_seconds

    def audio(self) -> Any:
        import numpy

        if self._frames:
            return numpy.concatenate(self._frames)
        return numpy.zeros(0, dtype="float32")


def record_until_silence(
    max_seconds: float = DEFAULT_MAX_SECONDS,
    silence_seconds: float = DEFAULT_SILENCE_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    recorder: Optional[Callable[[], Any]] = None,
) -> Any:
    if recorder is not None:
        return recorder()
    import sounddevice

    vad_recorder: VadRecorder = VadRecorder(max_seconds, silence_seconds, sample_rate)
    with sounddevice.InputStream(
        samplerate=sample_rate, channels=1, dtype="float32", blocksize=VAD_BLOCK_SIZE
    ) as stream:
        while True:
            data, _ = stream.read(VAD_BLOCK_SIZE)
            if vad_recorder.feed(data[:, 0].copy()):
                break
    return vad_recorder.audio()


def sanity_check(seconds: float = 3.0, sample_rate: int = SAMPLE_RATE) -> None:
    import sounddevice

    print(f"Recording {seconds:.0f}s — speak now...")
    recording = sounddevice.rec(
        int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32"
    )
    sounddevice.wait()
    print("Playing it back...")
    sounddevice.play(recording, sample_rate)
    sounddevice.wait()
    print("Mic sanity check complete.")


if __name__ == "__main__":
    sanity_check()
