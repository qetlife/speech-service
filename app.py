"""HTTP API: POST /transcribe (raw audio in the body) → {"text": ...}."""

import asyncio
import hmac

from contextlib import asynccontextmanager

from fastapi                import FastAPI, HTTPException, Request
from starlette.concurrency  import run_in_threadpool

import config

from transcriber import InvalidAudio, VoskTranscriber


def create_app(transcriber=None) -> FastAPI:
    """The app; tests pass a fake transcriber, otherwise the Vosk model is loaded on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.transcriber = transcriber or VoskTranscriber(config.MODEL_PATH)
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
        return {"status": "ok", "model": request.app.state.transcriber.model_name}

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
