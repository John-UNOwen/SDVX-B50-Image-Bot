# sdvx-b50-image-bot — deployment image
# Local dev used Python 3.14; the container uses 3.12-slim for ecosystem
# stability and battle-tested wheels (discord.py / Pillow / numpy).
# Pinned to a full patch tag so the Python runtime (and the Debian snapshot
# that the apt-get below pulls its packages from) never drifts between builds.
FROM python:3.12.14-slim

# Pillow and numpy ship self-contained manylinux wheels, so no system packages
# are strictly required. zlib/jpeg are added only as a safety net.
# Caveat: which apt package versions are available depends on the bundled
# Debian snapshot of the pinned base image tag — bumping the Python patch tag
# may also change the apt package set. This must run as root at build time
# (before the USER appuser below); at runtime the non-root user cannot apt-get.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching when only app code changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY . .

# Create the non-root `appuser` (uid 1000) and pre-own the writable paths in
# the image. This is NOT the runtime guarantee on its own: those two paths are
# named-volume mount targets at deploy time, and relying on Docker copy-on-mount
# to propagate this ownership into a volume is host-dependent (user-namespace
# remapping) and does not repair a volume reused after being populated as root.
# The entrypoint re-owns both targets at every boot (under container root) and
# then drops privileges — see entrypoint.py.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /app/data /app/b50_render/.jacket_cache \
    && chown appuser:appuser /app/data /app/b50_render/.jacket_cache

# The entrypoint runs as container root at boot, fixes volume ownership for the
# mount targets, then drops privileges to appuser and execs the bot. The image
# MUST be launched through this entrypoint: it is what re-owns the named-volume
# mount targets and then drops to uid 1000. Overriding/omitting ENTRYPOINT or
# COMMAND (e.g. `docker run --entrypoint sh ...` or setting the CMD) would run
# the bot process as root — never do that except for local container debugging.
COPY entrypoint.py /usr/local/bin/entrypoint.py
ENTRYPOINT ["python", "/usr/local/bin/entrypoint.py"]

# DISCORD_TOKEN is provided at runtime via env / secret (see .env.example).
# (Command is launched by the entrypoint as appuser.)
