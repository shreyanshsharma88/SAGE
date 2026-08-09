from typing import Any, Optional

DEFAULT_THRESHOLD: float = 0.5
PREFERRED_WAKE_WORDS: tuple[str, ...] = ("hey_jarvis", "hey jarvis")
FALLBACK_WAKE_WORD: str = "alexa"


def resolve_wake_word(available: list[str]) -> str:
    for preferred in PREFERRED_WAKE_WORDS:
        normalized: str = preferred.replace(" ", "_")
        for candidate in available:
            if normalized in candidate:
                return candidate
    for candidate in available:
        if FALLBACK_WAKE_WORD in candidate:
            return candidate
    return available[0] if available else FALLBACK_WAKE_WORD


class WakeWordDetector:
    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        model: Any = None,
        model_key: Optional[str] = None,
    ) -> None:
        self._threshold: float = threshold
        self._model: Any = model
        self._model_key: Optional[str] = model_key

    def _ensure_model(self) -> Any:
        if self._model is None:
            import openwakeword.utils
            from openwakeword.model import Model

            openwakeword.utils.download_models()
            self._model = Model()
        if self._model_key is None:
            self._model_key = resolve_wake_word(list(self._model.models.keys()))
        return self._model

    def wake_word(self) -> str:
        self._ensure_model()
        return self._model_key if self._model_key is not None else FALLBACK_WAKE_WORD

    def score(self, chunk: Any) -> float:
        model = self._ensure_model()
        samples: Any = self._to_int16(chunk)
        predictions: dict[str, float] = model.predict(samples)
        key: str = self._model_key if self._model_key is not None else FALLBACK_WAKE_WORD
        return float(predictions.get(key, 0.0))

    def detected(self, chunk: Any) -> bool:
        return self.score(chunk) >= self._threshold

    def reset(self) -> None:
        if self._model is not None and hasattr(self._model, "reset"):
            self._model.reset()

    @staticmethod
    def _to_int16(chunk: Any) -> Any:
        import numpy

        array = numpy.asarray(chunk)
        if array.dtype == numpy.int16:
            return array
        clipped = numpy.clip(array, -1.0, 1.0)
        return (clipped * 32767.0).astype(numpy.int16)
