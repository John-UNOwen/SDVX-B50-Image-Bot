# sdvx-b50-image-bot

A Discord bot that renders a Sound Voltex **B50** image (top-50 VF) for any
public [Tachi](https://kamai.tachi.ac) (Kamaitachi) user.

```
/b50 <username> [mode]   ->  posts only the b50.png card (total VF is in the image)
                             mode: nabla (default) | exceed
                             username is optional if you're linked (/link)
/link <username>         ->  link your Discord account to your Tachi username
/unlink                  ->  remove your link
/invite                  ->  links to add the bot to a server or install it on
                             your account so /b50 works in DMs
```

## What it does

1. Reads the user's SDVX personal bests from the Tachi API
   (`/api/v1/users/{username}/games/sdvx/pbs/all`, public, no auth needed).
2. Computes the per-chart **Volforce (VF)** using the standard formula
   (`level × (score/1e7) × grade_coeff × clear_coeff × 20`), sorts, and keeps
   the top 50.
3. Renders a PNG via a Pillow renderer (gradient background, per-chart cards
   with jacket, difficulty / lamp / grade badges, score, rank, timestamp) and
   posts it to Discord.

Chart levels come straight from `chart.levelNum` in the Tachi response, so the
8 MB `music_db.xml` song database the reference web app bundles is **not**
needed.

## Project layout

```
bot.py              Discord bot (discord.py): /b50, /link, /unlink, /invite, /stats
tachi.py            Tachi client: fetch pbs, resolve levels, build top-50 rows
vf.py               VF calculation (coefficient tables + formula)
links.py            Discord-user <-> Tachi-username link store (SQLite)
stats.py            Query statistics recorder (SQLite) + /stats viewer
render.py           CLI test driver (no Discord) - python render.py <username>
b50_render/
  generate.py       Pillow image renderer (adapted)
  asset/*.ttf       fonts used for rendering
requirements.txt      direct, verified dependency pins (what you install)
requirements.lock     fully-pinned pip-freeze-style lock (direct + transitive)
.env.example
Dockerfile          container image for hosting the bot
docker-compose.yml  one-command deploy (with persisted jacket cache)
.dockerignore
```

## Setup

> **Python 3.12+ is required.** `numpy==2.5.2` (pinned in
> [`requirements.txt`](requirements.txt)) does not support Python 3.11 or older,
> so running this bot needs **CPython 3.12 or newer**. The local dev machine
> happens to run Python 3.14, and the Docker image uses `python:3.12-slim`; both
> satisfy this requirement.
>
> **Use a virtualenv.** This machine has several Python installs (Anaconda 3.13,
> python.org 3.13, python 3.14, plus the Microsoft Store alias), and the Anaconda
> one is known to crash. Using `.venv` from the working 3.14 avoids all of that.

```powershell
# 1) create a clean virtualenv from a Python 3.12+ interpreter (here C:\Python314)
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell; or `call .venv\Scripts\activate.bat` in cmd

# 2) install deps into .venv (see "Dependencies" below; .venv is gitignored)
python -m pip install -r requirements.txt

# 3) configure the bot token
copy .env.example .env              # then edit DISCORD_TOKEN
#    (create a bot at https://discord.com/developers/applications,
#     invite it to your server; slash commands need no special message intents)

# 4) test the pipeline without Discord (produces ./b50.png)
python render.py <username>

# 5) run the bot
python bot.py
```

## Dependencies

- [`requirements.txt`](requirements.txt) lists the **direct** dependencies pinned
  to the exact versions this project was developed and verified against. Install
  these into the venv with `python -m pip install -r requirements.txt`.
- [`requirements.lock`](requirements.lock) is the **fully-pinned lock** (pip-freeze
  style): every direct **and** transitive package is pinned to an exact `==`
  version, with all `>=` / `~=` ranges eliminated, targeted at **CPython 3.12+**.
  Use it when you need a bit-exact, reproducible environment:
  `python -m pip install -r requirements.lock`.
- **Offline note on the lock:** `requirements.lock` was generated *offline* (no
  network / no `pip` in the generation environment), so it was **not** produced by
  an actual `pip freeze` run. Its transitive set and versions were instead resolved
  from live PyPI release metadata (the newest release satisfying each dependency's
  constraint on CPython 3.12). Before depending on it, regenerate it on a machine
  with network access to confirm the exact versions:
  `python -m pip install -r requirements.txt && python -m pip freeze > requirements.lock`.

> **Windows quick start:** double-click `start.bat` at the repo root. It uses a
> single-instance launcher — it auto-stops any previous bot and refuses to
> double-run (prevents duplicate logins), uses the venv (creating it + installing
> deps on first run) and prompts you to set `DISCORD_TOKEN` in `.env` if missing.

> If you ever get a `python.exe`/`git.exe` "Application Error", it's almost always
> a stray interpreter from Anaconda being picked up. Always run through the venv
> (`python` resolves to `.venv`), or call the venv python explicitly:
> `.venv\Scripts\python.exe bot.py`.

## Deploy with Docker

> Requires Docker on the host (it is **not** installed on this dev machine).
> Local dev used Python 3.14; the container uses `python:3.12-slim` for stability.

```powershell
# provide the token to docker-compose (reads .env, or export DISCORD_TOKEN)
echo "DISCORD_TOKEN=your-bot-token-here" > .env

docker compose up -d --build
```

Or without compose:

```bash
docker build -t sdvx-b50-image-bot .
docker run -d --name sdvx-b50-image-bot \
  -e DISCORD_TOKEN=your-bot-token-here \
  -e LINKS_DB=/app/data/links.db \
  -e STATS_DB=/app/data/stats.db \
  -v b50-jacket-cache:/app/b50_render/.jacket_cache \
  -v b50-data:/app/data \
  --restart unless-stopped \
  sdvx-b50-image-bot
```

The jacket cache is a named volume, so covers aren't re-downloaded on every
restart. The SQLite databases (`links.db` and `stats.db`) also live on the
`b50-data` named volume, mounted at `/app/data`, so saved links and query
statistics survive container rebuilds. The DB paths are pointed there with the
`LINKS_DB` / `STATS_DB` env vars; outside Docker each defaults to `links.db`
/ `stats.db` next to the source file, and the parent directory is created
automatically.

The container runs as the non-root `appuser` (uid 1000). The two writable
paths, `/app/data` and `/app/b50_render/.jacket_cache`, are named-volume mount
targets. **Ownership of those volumes is fixed automatically at every boot**: the
image entrypoint (`entrypoint.py`) runs as container root, re-owns both mount
targets to `appuser`, then drops privileges to `appuser` and launches the bot.
This runs inside the container's own user namespace, so it does not depend on
how the host maps uid 1000 (user-namespace remapping) and it **also repairs
reused volumes** — including an old volume that was populated as `root` — so
you do not need `docker compose down -v` to fix permissions. Do not set
`user: appuser` (or `user: "1000"`) on the service in compose or override
`entrypoint:`, or the entrypoint cannot re-own the volumes and `/link`,
`/stats` and `/b50` will fail with permission errors on any host where the
volume ownership does not already match.

## Notes & limitations

- Works only for **public** Tachi profiles; private profiles return an error.
- Renders can take tens of seconds while jackets download (cached afterward in
  `b50_render/.jacket_cache/`), so the command is deferred.
- **Python version:** **CPython 3.12+ is required** (see Setup); Python 3.11 and
  older are **not** supported because the pinned `numpy==2.5.2` needs >=3.12.
  The code was written against Python 3.14; the Docker image ships on
  `python:3.12-slim`. There is no supported configuration on Python 3.11.
- `diff` and `lamp` strings are pulled straight from Tachi and mapped to the
  renderer's badge styles; unmapped values fall back gracefully.
- **Verified correctness:** the VF calculation matches Tachi's own
  `calculatedData.VF7` (current / Nabla) and `VF6` (Exceed Gear) exactly — 2551/2551
  charts on a live sample.
- **Logging:** every Tachi lookup, link action, command invocation and render is
  logged to the console. `INFO` (default) logs one line per action; set
  `LOG_LEVEL=DEBUG` in `.env` (or the environment) for per-request detail.
- **Statistics:** every command invocation (type, `/b50` mode, user, target) is
  recorded in `stats.db` (gitignored); `/stats` shows the totals.
- **Rate limiting:** `/b50` is limited to one run per user per 10 seconds and
  at most four images render at once; jacket downloads are retried on
  transient failures, so a burst of requests can't hammer Tachi or the
  cover-art service.
- **Slash command visibility:** global sync (used for DMs + all servers) can
  take up to ~1 hour to appear in clients. Set `GUILD_ID` in `.env` for
  instant availability in your own server. Commands in **DMs** additionally
  require the app to have a **Privacy Policy URL** set in the Developer Portal
  (Apps → General Information).

## Credit / license

- Image renderer and VF math adapted from
  [whiteou7/new-vf-calc](https://github.com/whiteou7/new-vf-calc) (**MIT**, © 2025 Tung Vu).
- Fonts: Poppins, IBM Plex Sans JP, Noto Sans (all OFL).
