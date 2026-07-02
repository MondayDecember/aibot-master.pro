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
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
