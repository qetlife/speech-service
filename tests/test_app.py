import pytest

from fastapi.testclient import TestClient

import app as app_module
import config

from tests.conftest import make_audio
from transcriber import InvalidAudio, Transcript, to_pcm


class FakeTranscriber:
    model_name = "fake-model"

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, max_seconds):
        self.calls.append(max_seconds)
        pcm = to_pcm(audio, max_seconds)  # real decoding, fake recognition
        return Transcript(text="remind me tomorrow at nine to call mom", duration=round(len(pcm) / 32000, 2))


@pytest.fixture
def fake():
    return FakeTranscriber()


class FakeSpeaker:
    voice_name = "fake-voice"

    def __init__(self):
        self.texts = []

    def speak(self, text):
        self.texts.append(text)
        return make_audio(0.5, codec="pcm_s16le", fmt="wav")


@pytest.fixture
def speaker():
    return FakeSpeaker()


@pytest.fixture
def client(fake, speaker):
    with TestClient(app_module.create_app(transcriber=fake, speaker=speaker)) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "model": "fake-model", "voice": "fake-voice"}


def test_health_without_a_voice(fake):
    with TestClient(app_module.create_app(transcriber=fake, speaker=None)) as c:
        assert c.get("/health").json()["voice"] is None


def test_transcribe(client, voice_ogg):
    response = client.post("/transcribe", content=voice_ogg, headers={"content-type": "audio/ogg"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "remind me tomorrow at nine to call mom"
    assert body["model"] == "fake-model"
    assert 0.9 < body["duration"] < 1.1


def test_invalid_audio_is_400(client):
    response = client.post("/transcribe", content=b"not audio")
    assert response.status_code == 400
    assert "decode" in response.json()["detail"]


def test_empty_body_is_400(client):
    assert client.post("/transcribe", content=b"").status_code == 400


def test_too_large_is_413(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    assert client.post("/transcribe", content=b"x" * 10).status_code == 413


def test_max_seconds_is_capped(client, fake, voice_ogg, monkeypatch):
    monkeypatch.setattr(config, "MAX_SECONDS", 30)
    client.post("/transcribe?max_seconds=5", content=voice_ogg)
    client.post("/transcribe?max_seconds=500", content=voice_ogg)
    assert fake.calls == [5, 30]
    assert client.post("/transcribe?max_seconds=abc", content=voice_ogg).status_code == 400


def test_api_token(client, voice_ogg, monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret")
    assert client.post("/transcribe", content=voice_ogg).status_code == 401
    assert client.post("/transcribe", content=voice_ogg, headers={"authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/transcribe", content=voice_ogg, headers={"authorization": "Bearer secret"}).status_code == 200


def test_transcriber_errors_other_than_bad_audio_are_500(fake, voice_ogg):
    def boom(audio, max_seconds):
        raise RuntimeError("model crashed")

    fake.transcribe = boom
    with TestClient(app_module.create_app(transcriber=fake, speaker=None), raise_server_exceptions=False) as c:
        assert c.post("/transcribe", content=voice_ogg).status_code == 500


def test_invalid_audio_from_transcriber_is_400(fake, voice_ogg):
    def bad(audio, max_seconds):
        raise InvalidAudio("Couldn't decode the audio.")

    fake.transcribe = bad
    with TestClient(app_module.create_app(transcriber=fake, speaker=None)) as c:
        assert c.post("/transcribe", content=voice_ogg).status_code == 400


# --- /speak ---------------------------------------------------------------------

@pytest.mark.parametrize("fmt, media_type, magic", [
    ("wav", "audio/wav", b"RIFF"), ("mp3", "audio/mpeg", None), ("ogg", "audio/ogg", b"OggS"),
])
def test_speak(client, speaker, fmt, media_type, magic):
    response = client.post("/speak", json={"text": "  Got it:\n call mom ", "format": fmt})
    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    assert response.headers["x-voice"] == "fake-voice"
    if magic:
        assert response.content.startswith(magic)
    assert len(to_pcm(response.content, 120)) > 0
    # Whitespace is folded
    assert speaker.texts == ["Got it: call mom"]


def test_speak_defaults_to_wav(client):
    assert client.post("/speak", json={"text": "hi"}).headers["content-type"] == "audio/wav"


@pytest.mark.parametrize("body, status", [
    ({"text": "   "}, 400), ({"text": "x" * 1001}, 413), ({}, 422), ({"text": "hi", "format": "flac"}, 422),
])
def test_speak_rejects(client, body, status):
    assert client.post("/speak", json=body).status_code == status


def test_speak_without_a_voice_is_503(fake):
    with TestClient(app_module.create_app(transcriber=fake, speaker=None)) as c:
        assert c.post("/speak", json={"text": "hi"}).status_code == 503


def test_speak_needs_the_token(client, monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "secret")
    assert client.post("/speak", json={"text": "hi"}).status_code == 401
    assert client.post("/speak", json={"text": "hi"}, headers={"authorization": "Bearer secret"}).status_code == 200
