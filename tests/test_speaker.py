import os

import pytest

import config

from speaker     import AudioFormat, PiperSpeaker, encode
from tests.conftest import make_audio
from transcriber import BYTES_PER_SECOND, to_pcm


@pytest.mark.parametrize("fmt", list(AudioFormat))
def test_encode_keeps_the_audio(fmt):
    wav = make_audio(1.0, codec="pcm_s16le", fmt="wav")
    audio = encode(wav, fmt)
    assert abs(len(to_pcm(audio, 120)) / BYTES_PER_SECOND - 1.0) < 0.1
    if fmt == AudioFormat.WAV:
        assert audio == wav


# --- real voice (CI downloads it; skipped when it isn't there) ---------------

needs_voice = pytest.mark.skipif(not os.path.isfile(config.VOICE_PATH), reason="Piper voice not downloaded")


@needs_voice
def test_piper_speaks():
    speaker = PiperSpeaker(config.VOICE_PATH)
    assert speaker.voice_name == "en_US-lessac-medium"
    wav = speaker.speak("Got it: call mom, tomorrow at nine.")
    assert wav.startswith(b"RIFF")
    # A second or more of speech
    assert len(to_pcm(wav, 120)) / BYTES_PER_SECOND > 1.0
