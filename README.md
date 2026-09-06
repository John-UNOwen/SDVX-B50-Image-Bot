# sdvx-b50-discord-bot

A Discord bot that renders a Sound Voltex **B50** image (top-50 VF) for any
public [Tachi](https://kamai.tachi.ac) (Kamaitachi) user.

```
/b50 <username> [mode]   ->  posts only the b50.png card (total VF is in the image)
                             mode: nabla (default) | exceed
                             username is optional if you're linked (/link)
/link <username>         ->  link your Discord account to your Tachi username
/unlink                  ->  remove your link
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
bot.py              Discord bot (discord.py): /b50, /link, /unlink, /stats
tachi.py            Tachi client: fetch pbs, resolve levels, build top-50 rows
vf.py               VF calculation (coefficient tables + formula)
links.py            Discord-user <-> Tachi-username link store (SQLite)
stats.py            Query statistics recorder (SQLite) + /stats viewer
render.py           CLI test driver (no Discord) - python render.py <username>
b50_render/
  generate.py       Pillow image renderer (adapted)
  asset/*.ttf       fonts used for rendering
requirements.txt
.env.example
Dockerfile          container image for hosting the bot
docker-compose.yml  one-command deploy (with persisted jacket cache)
.dockerignore
```

## Setup

> **Use a virtualenv.** This machine has several Python installs (Anaconda 3.13,
> python.org 3.13, python 3.14, plus the Microsoft Store alias), and the Anaconda
> one is known to crash. Using `.venv` from the working 3.14 avoids all of that.

```powershell
# 1) create a clean virtualenv from the working interpreter (C:\Python314)
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell; or `call .venv\Scripts\activate.bat` in cmd

# 2) install deps (into .venv; .venv is gitignored)
python -m pip install -r requirements.txt

# 3) configure the bot token
copy .env.example .env              # then edit DISCORD_TOKEN
#    (create a bot at https://discord.com/developers/applications,
#     enable the Message Content intent, invite it to your server)

# 4) test the pipeline without Discord (produces ./b50.png)
python render.py <username>

# 5) run the bot
python bot.py
```

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
docker build -t sdvx-b50-bot .
docker run -d --name sdvx-b50-bot \
  -e DISCORD_TOKEN=your-bot-token-here \
  -v b50-jacket-cache:/app/b50_render/.jacket_cache \
  --restart unless-stopped \
  sdvx-b50-bot
```

The jacket cache is a named volume, so covers aren't re-downloaded on every restart.

## Notes & limitations

- Works only for **public** Tachi profiles; private profiles return an error.
- Renders can take tens of seconds while jackets download (cached afterward in
  `b50_render/.jacket_cache/`), so the command is deferred.
- **Python 3.x compatibility:** `discord.py` historically lags the newest CPython
  releases. This was written against Python 3.14; if `discord.py` fails to install
  or import, use Python 3.11–3.12 or pin to a newer `discord.py`/`nextcord` build.
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
- **Slash command visibility:** global sync (used for DMs + all servers) can
  take up to ~1 hour to appear in clients. Set `GUILD_ID` in `.env` for
  instant availability in your own server. Commands in **DMs** additionally
  require the app to have a **Privacy Policy URL** set in the Developer Portal
  (Apps → General Information).

## Credit / license

- Image renderer and VF math adapted from
  [whiteou7/new-vf-calc](https://github.com/whiteou7/new-vf-calc) (**MIT**, © 2025 Tung Vu).
- Fonts: Poppins, IBM Plex Sans JP, Noto Sans (all OFL).
