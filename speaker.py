"""Text → audio: Piper speaks the text (WAV), ffmpeg turns it into MP3 or OGG/Opus if asked."""

import io
import os
import subprocess
import wave

from enum import Enum


FFMPEG_TIMEOUT = 60     # seconds


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"         # Opus in OGG, the smallest


MEDIA_TYPES = {AudioFormat.WAV: "audio/wav", AudioFormat.MP3: "audio/mpeg", AudioFormat.OGG: "audio/ogg"}
ENCODERS = {AudioFormat.MP3: ["-c:a", "libmp3lame", "-q:a", "5", "-f", "mp3"],
            AudioFormat.OGG: ["-c:a", "libopus", "-b:a", "32k", "-f", "ogg"]}


class EncodingFailed(RuntimeError):
    """ffmpeg couldn't encode the speech."""


def encode(wav: bytes, fmt: AudioFormat) -> bytes:
    """WAV → `fmt` (WAV as it is)."""
    if fmt == AudioFormat.WAV:
        return wav
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *ENCODERS[fmt], "pipe:1"],
            input=wav, capture_output=True, timeout=FFMPEG_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise EncodingFailed("Encoding the speech took too long.") from e
    if result.returncode != 0 or not result.stdout:
        raise EncodingFailed(result.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    return result.stdout


class PiperSpeaker:
    """Loads the Piper voice once; speak() can run from several threads."""

    def __init__(self, voice_path: str):
        from piper import PiperVoice  # imported here so tests can run without the voice

        self.voice_name = os.path.basename(voice_path).removesuffix(".onnx")
        self.voice = PiperVoice.load(voice_path)

    def speak(self, text: str) -> bytes:
        """The text spoken, as WAV."""
        out = io.BytesIO()
        with wave.open(out, "wb") as wav:
            self.voice.synthesize_wav(text, wav)
        return out.getvalue()
