FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ffmpeg decodes any audio format to what Vosk expects
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Vosk model, downloaded at build time. This layer is cached until VOSK_MODEL
# changes, so normal deploys don't download it again.
# Models: https://alphacephei.com/vosk/models
ARG VOSK_MODEL=vosk-model-small-en-us-0.15
RUN python -c "import io, urllib.request, zipfile; \
url = 'https://alphacephei.com/vosk/models/${VOSK_MODEL}.zip'; \
zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).extractall('/models')"
ENV MODEL_PATH=/models/${VOSK_MODEL}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
