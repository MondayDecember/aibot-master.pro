FROM python:3.11-slim

# Install system dependencies
# ffmpeg is required by faster-whisper to process audio files
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Run as a non-root user. uid 1000 matches the default first user on most
# Linux hosts, so the bind-mounted ./data directory stays writable.
# /home/appuser/.cache is created here (not left for the whisper_cache named
# volume to create on first mount) so it's already owned by appuser - an
# empty root-owned mountpoint is what caused the faster-whisper "Permission
# denied" crash.
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /home/appuser/.cache && \
    chown -R appuser:appuser /app /home/appuser
USER appuser

CMD ["python", "main.py"]
