import os
import subprocess
import sys

import pytest

# Make the top-level modules (app, config, transcriber) importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_audio(seconds: float = 1.0, codec: str = "libopus", fmt: str = "ogg", source: str = "sine") -> bytes:
    """Generate audio with ffmpeg; OGG/Opus is what Telegram voice messages are."""
    src = f"sine=frequency=440:duration={seconds}" if source == "sine" else f"anullsrc=r=48000:cl=mono:d={seconds}"
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src,
         "-c:a", codec, "-f", fmt, "pipe:1"],
        capture_output=True, check=True,
    ).stdout


@pytest.fixture
def voice_ogg():
    return make_audio(1.0)
