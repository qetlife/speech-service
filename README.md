# speech-service

Offline speech-to-text and text-to-speech for the projects on the Raspberry
Pi. A small HTTP service around [Vosk](https://alphacephei.com/vosk/),
[Piper](https://github.com/OHF-Voice/piper1-gpl) and ffmpeg: send it audio in
any format and get the text back, or send it text and get it spoken. Free,
and neither audio nor text ever leaves the Pi.

Used by [roman-tech-bot](https://github.com/qetlife/roman-tech-bot) for voice
messages and the web app's spoken replies; any project on `shared-network`
can use it.

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

### `POST /speak`

The text, spoken by Piper. JSON body:

```json
{"text": "Got it: call mom, tomorrow at 09:00.", "format": "mp3"}
```

- `text`: up to `MAX_SPEAK_CHARS` characters; whitespace is folded.
- `format` (optional): `wav` (default), `mp3`, or `ogg` (Opus, the smallest).
  Browsers play `mp3` everywhere; Safari is unreliable with `ogg`.

The response body is the audio (`audio/wav`, `audio/mpeg` or `audio/ogg`), with
the voice's name in an `X-Voice` header.

```bash
curl -H 'content-type: application/json' -d '{"text": "hello", "format": "mp3"}' \
  http://speech:8000/speak -o hello.mp3
```

| Status | When |
| ------ | ---- |
| 200 | Spoken |
| 400 | Empty text |
| 401 | `API_TOKEN` is set and the request has no or a wrong token |
| 413 | Longer than `MAX_SPEAK_CHARS` |
| 422 | Not JSON, no `text`, or an unknown `format` |
| 503 | No voice installed (the image was built without it) |

### `GET /health`

`{"status": "ok", "model": "vosk-model-small-en-us-0.15", "voice": "en_US-lessac-medium"}`
once the model is loaded; `voice` is `null` without a voice (then `/speak`
answers 503).

## Configuration

Environment variables (in `.env` next to `docker-compose.yml`, all optional):

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `VOSK_MODEL` | `vosk-model-small-en-us-0.15` | Model baked into the image at build time ([list](https://alphacephei.com/vosk/models)) |
| `PIPER_VOICE` | `en_US-lessac-medium` | Voice baked into the image at build time ([list](https://huggingface.co/rhasspy/piper-voices); `<lang>_<REGION>-<name>-<quality>`) |
| `API_TOKEN` | *(none)* | If set, `/transcribe` and `/speak` require `Authorization: Bearer <API_TOKEN>` |
| `MAX_UPLOAD_MB` | `10` | Largest accepted upload |
| `MAX_SECONDS` | `120` | Longer audio is cut to this length |
| `MAX_CONCURRENT` | `2` | Transcriptions and speech at the same time; more wait their turn |
| `MAX_SPEAK_CHARS` | `1000` | Longest text `/speak` takes |

**Models.** The small English model (~40 MB, a few hundred MB of RAM) is fast
on a Pi 4/5 and good for short, clear commands. For better accuracy, try
`vosk-model-en-us-0.22-lgraph` (~130 MB, more RAM, slower): set `VOSK_MODEL`
and redeploy.

**Voices.** `en_US-lessac-medium` (~60 MB) speaks a short reply in well under
a second on a Pi 5. `-high` voices sound better and are slower; `-low` ones
are faster. Set `PIPER_VOICE` and redeploy. Piper is GPL-3.0 licensed; the
service only uses it as a library.

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

1. `test` runs pyflakes and pytest on a GitHub-hosted runner, including tests
   against the real Vosk model and Piper voice.
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

The real-model tests run only when the model and the voice are present
(`MODEL_PATH`, default `models/vosk-model-small-en-us-0.15`; `VOICE_PATH`,
default `voices/en_US-lessac-medium.onnx`):

```bash
mkdir -p models && curl -sSL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/m.zip && unzip -q /tmp/m.zip -d models
mkdir -p voices && for ext in onnx onnx.json; do curl -sSL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.$ext" -o "voices/en_US-lessac-medium.$ext"; done
uvicorn app:app --reload                 # http://localhost:8000/docs
```

### Files

```
app.py            HTTP API (FastAPI): /transcribe, /speak, /health
transcriber.py    ffmpeg decoding + Vosk transcription
speaker.py        Piper speech + ffmpeg encoding
config.py         environment variables
tests/            pytest; audio is generated with ffmpeg
Dockerfile        ffmpeg + model + voice + app
docker-compose.yml
```
