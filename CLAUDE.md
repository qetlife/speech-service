# speech-service

Offline speech-to-text and text-to-speech HTTP service (FastAPI + Vosk +
Piper + ffmpeg) for projects on the Raspberry Pi. See `README.md`.

## Rules

- **The API is a contract**: `POST /transcribe` (raw audio body) → `{"text",
  "duration", "model"}`, `POST /speak` (`{"text", "format"}`) → audio, and
  `GET /health`. Other projects depend on it; add
  fields, never rename or remove them.
- **Keep docs up to date in the same change**: `README.md` (API, configuration,
  deployment).
- Configuration comes from environment variables in `config.py`; document new
  ones in the README table and `docker-compose.yml`.
- Run `python -m pyflakes *.py tests` and `pytest` before pushing; every push to
  `master` deploys to the Pi.
