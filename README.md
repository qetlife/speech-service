# speech-service

Offline speech-to-text for the projects on the Raspberry Pi. A small HTTP
service around [Vosk](https://alphacephei.com/vosk/) and ffmpeg: send it audio
in any format, get the text back. Free, and audio never leaves the Pi.

Used by [roman-tech-bot](https://github.com/qetlife/roman-tech-bot) for voice
messages; any project on `shared-network` can use it.

## API

### `POST /transcribe`

The request body is the audio file as it is: OGG/Opus (Telegram voice
messages), MP3, WAV, M4A, … anything ffmpeg reads. No form fields, no
conversion needed on the client.

```bash
curl --data-binary @voice.ogg http://speech:8000/transcribe
```

```json
{"text": "remind me tomorrow at nine to call mom", "duration": 3.2, "model": "vosk-model-small-en-us-0.15"}
```

- `text`: lowercase words, no punctuation; numbers come out as words
  (“nine thirty”). Empty if nothing was understood.
- `duration`: seconds of audio transcribed.
- Optional query parameter `max_seconds=N` to cut the audio shorter than the
  server's limit.

| Status | When |
| ------ | ---- |
| 200 | Transcribed (`text` may be empty) |
| 400 | Empty body or not decodable audio; bad `max_seconds` |
| 401 | `API_TOKEN` is set and the request has no or a wrong `Authorization: Bearer <token>` |
| 413 | Larger than `MAX_UPLOAD_MB` |

From Python:

```python
import httpx

response = httpx.post("http://speech:8000/transcribe", content=audio_bytes, timeout=60)
response.raise_for_status()
text = response.json()["text"]
```

### `GET /health`

`{"status": "ok", "model": "vosk-model-small-en-us-0.15"}` once the model is
loaded.

## Configuration

Environment variables (in `.env` next to `docker-compose.yml`, all optional):

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `VOSK_MODEL` | `vosk-model-small-en-us-0.15` | Model baked into the image at build time ([list](https://alphacephei.com/vosk/models)) |
| `API_TOKEN` | *(none)* | If set, `/transcribe` requires `Authorization: Bearer <API_TOKEN>` |
| `MAX_UPLOAD_MB` | `10` | Largest accepted upload |
| `MAX_SECONDS` | `120` | Longer audio is cut to this length |
| `MAX_CONCURRENT` | `2` | Transcriptions at the same time; more wait their turn |

**Models.** The small English model (~40 MB, a few hundred MB of RAM) is fast
on a Pi 4/5 and good for short, clear commands. For better accuracy, try
`vosk-model-en-us-0.22-lgraph` (~130 MB, more RAM, slower): set `VOSK_MODEL`
and redeploy.

## Running on the Pi

The service joins the external Docker network `shared-network` (where
`postgres` and the bot run) as `speech`, with no published ports, so it is
only reachable from other containers: `http://speech:8000`.

First-time setup:

```bash
docker network create shared-network     # if it doesn't exist yet
git clone https://github.com/qetlife/speech-service /home/apps/speech-service
cd /home/apps/speech-service
docker compose up -d --build             # downloads the model on the first build
docker compose exec speech python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"
```

Try it from the Pi with any audio file:

```bash
docker run --rm --network shared-network -v "$PWD:/a" curlimages/curl \
  --data-binary @/a/voice.ogg http://speech:8000/transcribe
```

## Deployment

Every push to `master` runs the tests and, if they pass, deploys to the Pi
(`.github/workflows/deploy.yml`):

1. `test` runs pyflakes and pytest on a GitHub-hosted runner, including a test
   against the real Vosk model.
2. `deploy` runs on a self-hosted runner on the Pi with the label
   `speech-service`. It resets `/home/apps/speech-service` to the tested
   commit, rebuilds, and fails unless `/health` answers within a minute.

Register the runner once: GitHub → repo **Settings → Actions → Runners → New
self-hosted runner**, follow the steps on the Pi, and add the label
`speech-service`. Until it exists, deploy jobs wait in the queue; deploy by
hand with `docker compose up -d --build`.

## Development

```bash
pip install -r requirements-dev.txt      # also needs ffmpeg installed
python -m pyflakes *.py tests
pytest
```

The real-model test runs only when the model is present
(`MODEL_PATH`, default `models/vosk-model-small-en-us-0.15`):

```bash
mkdir -p models && curl -sSL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/m.zip && unzip -q /tmp/m.zip -d models
uvicorn app:app --reload                 # http://localhost:8000/docs
```

### Files

```
app.py            HTTP API (FastAPI): /transcribe, /health
transcriber.py    ffmpeg decoding + Vosk transcription
config.py         environment variables
tests/            pytest; audio is generated with ffmpeg
Dockerfile        ffmpeg + model + app
docker-compose.yml
```
