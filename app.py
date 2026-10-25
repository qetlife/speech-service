"""HTTP API: POST /transcribe (raw audio in the body) → {"text": ...}; POST /speak {"text"} → audio."""

import asyncio
import hmac
import logging
import os

from contextlib import asynccontextmanager

from fastapi                import FastAPI, HTTPException, Request, Response
from pydantic               import BaseModel
from starlette.concurrency  import run_in_threadpool

import config

from speaker     import MEDIA_TYPES, AudioFormat, EncodingFailed, PiperSpeaker, encode
from transcriber import InvalidAudio, VoskTranscriber


logger = logging.getLogger(__name__)

# Not given: load the real one (the voice only if it's there)
REAL = object()


class SpeakRequest(BaseModel):
    text: str
    format: AudioFormat = AudioFormat.WAV


def _load_speaker():
    if not os.path.isfile(config.VOICE_PATH):
        logger.warning("No Piper voice at %s: /speak is off", config.VOICE_PATH)
        return None
    return PiperSpeaker(config.VOICE_PATH)


def create_app(transcriber=None, speaker=REAL) -> FastAPI:
    """The app; tests pass fakes, otherwise the Vosk model and the Piper voice are loaded on startup.

    `speaker=None`: no voice, /speak answers 503.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.transcriber = transcriber or VoskTranscriber(config.MODEL_PATH)
        app.state.speaker = _load_speaker() if speaker is REAL else speaker
        app.state.slots = asyncio.Semaphore(config.MAX_CONCURRENT)
        yield

    app = FastAPI(title="speech-service", lifespan=lifespan)

    def check_token(request: Request):
        if config.API_TOKEN is None:
            return
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given, config.API_TOKEN):
            raise HTTPException(status_code=401, detail="Missing or wrong API token.")

    @app.get("/health")
    async def health(request: Request):
        voice = request.app.state.speaker.voice_name if request.app.state.speaker is not None else None
        return {"status": "ok", "model": request.app.state.transcriber.model_name, "voice": voice}

    @app.post("/speak")
    async def speak(body: SpeakRequest, request: Request):
        """{"text": "...", "format": "wav" | "mp3" | "ogg"} → the text spoken, as audio."""
        check_token(request)
        if request.app.state.speaker is None:
            raise HTTPException(status_code=503, detail="No voice installed.")
        text = " ".join(body.text.split())
        if not text:
            raise HTTPException(status_code=400, detail="Empty text.")
        if len(text) > config.MAX_SPEAK_CHARS:
            raise HTTPException(status_code=413, detail=f"Text longer than {config.MAX_SPEAK_CHARS} characters.")
        async with request.app.state.slots:
            wav = await run_in_threadpool(request.app.state.speaker.speak, text)
            try:
                audio = await run_in_threadpool(encode, wav, body.format)
            except EncodingFailed as e:
                raise HTTPException(status_code=500, detail=str(e))
        return Response(content=audio, media_type=MEDIA_TYPES[body.format],
                        headers={"X-Voice": request.app.state.speaker.voice_name})

    @app.post("/transcribe")
    async def transcribe(request: Request):
        """Body: the audio file as it is (any format ffmpeg reads). Optional ?max_seconds=N."""
        check_token(request)

        limit = config.MAX_UPLOAD_MB * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise HTTPException(status_code=413, detail=f"Audio larger than {config.MAX_UPLOAD_MB} MB.")
        audio = await request.body()
        if len(audio) > limit:
            raise HTTPException(status_code=413, detail=f"Audio larger than {config.MAX_UPLOAD_MB} MB.")

        try:
            max_seconds = min(int(request.query_params.get("max_seconds", config.MAX_SECONDS)), config.MAX_SECONDS)
        except ValueError:
            raise HTTPException(status_code=400, detail="max_seconds must be a whole number.")

        async with request.app.state.slots:
            try:
                result = await run_in_threadpool(request.app.state.transcriber.transcribe, audio, max_seconds)
            except InvalidAudio as e:
                raise HTTPException(status_code=400, detail=str(e))

        return {"text": result.text, "duration": result.duration, "model": request.app.state.transcriber.model_name}

    return app


app = create_app()
