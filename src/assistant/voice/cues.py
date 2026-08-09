from assistant.config import SAMPLE_RATE

BEEP_FREQUENCY: float = 880.0
BEEP_DURATION: float = 0.15
BEEP_AMPLITUDE: float = 0.3


def play_beep(
    frequency: float = BEEP_FREQUENCY,
    duration: float = BEEP_DURATION,
    sample_rate: int = SAMPLE_RATE,
) -> None:
    import numpy
    import sounddevice

    samples = numpy.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    tone = (BEEP_AMPLITUDE * numpy.sin(2.0 * numpy.pi * frequency * samples)).astype("float32")
    sounddevice.play(tone, sample_rate)
