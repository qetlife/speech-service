"""Audio → text: ffmpeg converts any audio to 16 kHz mono PCM, Vosk transcribes it."""

import json
import os
import subprocess

from dataclasses import dataclass


SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2      # 16-bit mono
CHUNK = 4000 * 2                        # 0.25 s of audio per Vosk call
FFMPEG_TIMEOUT = 60                     # seconds


class InvalidAudio(ValueError):
    """The upload isn't audio ffmpeg can decode (or it's empty)."""


@dataclass
class Transcript:
    text: str
    duration: float     # seconds of audio transcribed


def to_pcm(audio: bytes, max_seconds: int) -> bytes:
    """Decode any audio format (OGG/Opus, MP3, WAV, ...) to 16 kHz mono 16-bit PCM."""
    if not audio:
        raise InvalidAudio("Empty audio.")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0", "-t", str(max_seconds),
                "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
            ],
            input=audio, capture_output=True, timeout=FFMPEG_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise InvalidAudio("Decoding the audio took too long.") from e
    if result.returncode != 0 or not result.stdout:
        error = result.stderr.decode(errors="replace").strip().splitlines()
        raise InvalidAudio("Couldn't decode the audio" + (f": {error[-1]}" if error else "."))
    return result.stdout


class VoskTranscriber:
    """Loads the Vosk model once; transcribe() can run from several threads."""

    def __init__(self, model_path: str):
        import vosk  # imported here so tests can run without the model

        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self.model_name = os.path.basename(os.path.normpath(model_path))
        self.model = vosk.Model(model_path)

    def transcribe(self, audio: bytes, max_seconds: int) -> Transcript:
        pcm = to_pcm(audio, max_seconds)
        recognizer = self._vosk.KaldiRecognizer(self.model, SAMPLE_RATE)
        parts = []
        for start in range(0, len(pcm), CHUNK):
            # True at the end of an utterance: collect it before it's replaced.
            if recognizer.AcceptWaveform(pcm[start:start + CHUNK]):
                parts.append(json.loads(recognizer.Result()).get("text", ""))
        parts.append(json.loads(recognizer.FinalResult()).get("text", ""))
        text = " ".join(p for p in parts if p)
        return Transcript(text=text, duration=round(len(pcm) / BYTES_PER_SECOND, 2))
