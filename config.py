"""Settings from the environment."""

import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# Folder of the unpacked Vosk model (set by the Dockerfile).
MODEL_PATH = os.environ.get("MODEL_PATH", "models/vosk-model-small-en-us-0.15")
# Optional shared secret: if set, requests need "Authorization: Bearer <API_TOKEN>".
API_TOKEN = os.environ.get("API_TOKEN") or None
# Largest accepted upload, in megabytes.
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)
# Longer audio is cut to this many seconds.
MAX_SECONDS = _int("MAX_SECONDS", 120)
# Transcriptions running at the same time; more wait (keeps the Pi responsive).
MAX_CONCURRENT = _int("MAX_CONCURRENT", 2)
