from typing import Any, Optional

from assistant.config import SAMPLE_RATE, get_config


class WhisperSTT:
    def __init__(self, model_name: Optional[str] = None, model: Any = None) -> None:
        self._model_name: str = model_name if model_name is not None else get_config().whisper_model
        self._model: Any = model

    def _ensure_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: Any, sample_rate: int = SAMPLE_RATE) -> str:
        model = self._ensure_model()
        segments, _ = model.transcribe(audio, language="en", vad_filter=True)
        text: str = " ".join(segment.text.strip() for segment in segments).strip()
        return text
