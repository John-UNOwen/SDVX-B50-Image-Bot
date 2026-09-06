# sdvx-b50-image-bot — deployment image
# Local dev used Python 3.14; the container uses 3.12-slim for ecosystem
# stability and battle-tested wheels (discord.py / Pillow / numpy).
FROM python:3.12-slim

# Pillow and numpy ship self-contained manylinux wheels, so no system packages
# are strictly required. zlib/jpeg are added only as a safety net.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching when only app code changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# DISCORD_TOKEN is provided at runtime via env / secret (see .env.example).
CMD ["python", "bot.py"]
