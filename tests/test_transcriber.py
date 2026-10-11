import os

import pytest

import config

from tests.conftest import make_audio
from transcriber import BYTES_PER_SECOND, InvalidAudio, VoskTranscriber, to_pcm


@pytest.mark.parametrize("codec, fmt", [("libopus", "ogg"), ("pcm_s16le", "wav"), ("libmp3lame", "mp3")])
def test_to_pcm_decodes_common_formats(codec, fmt):
    pcm = to_pcm(make_audio(1.0, codec=codec, fmt=fmt), max_seconds=120)
    # About one second of 16 kHz mono 16-bit audio (encoders add a few ms of padding).
    assert abs(len(pcm) / BYTES_PER_SECOND - 1.0) < 0.1


def test_to_pcm_cuts_long_audio():
    pcm = to_pcm(make_audio(3.0), max_seconds=1)
    assert len(pcm) / BYTES_PER_SECOND <= 1.05


@pytest.mark.parametrize("audio", [b"", b"this is not audio"])
def test_to_pcm_rejects_invalid_audio(audio):
    with pytest.raises(InvalidAudio):
        to_pcm(audio, max_seconds=120)


# --- real model (CI downloads it; skipped when it isn't there) ---------------

needs_model = pytest.mark.skipif(not os.path.isdir(config.MODEL_PATH), reason="Vosk model not downloaded")


@needs_model
def test_vosk_transcribes_silence_as_empty_text():
    transcriber = VoskTranscriber(config.MODEL_PATH)
    result = transcriber.transcribe(make_audio(2.0, source="silence"), max_seconds=120)
    assert result.text == ""
    assert abs(result.duration - 2.0) < 0.1
