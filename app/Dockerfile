FROM python:3.12-slim

# No apt packages: PyAV brings its own ffmpeg libraries for Whisper.
# yt-dlp needs a JavaScript runtime to solve YouTube's player challenges.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tamlil ./tamlil
COPY tests ./tests

ENV PYTHONUNBUFFERED=1 HF_HOME=/models TAMLIL_DATA=/data
EXPOSE 8000
CMD ["uvicorn", "tamlil.web:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
