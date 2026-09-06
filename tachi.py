"""Tachi / Kamaitachi client — fetch a user's SDVX personal bests.

The B50 pipeline needs every chart the player has a PB on; we compute VF per
chart and keep the top 50. Data is read (unauthenticated) from the Tachi JSON API:

    GET https://kamai.tachi.ac/api/v1/users/{username}/games/sdvx/pbs/all

which returns ``{ body: { pbs: [...], charts: [...] }, ... }``.

Verified against the live schema (2025):
  * ``charts[]`` items carry ``level`` / ``levelNum`` (chart level),
    ``difficulty`` (NOV/ADV/EXH/INF/GRV/HVN/VVD/XCD/MXM/ULT), ``song.title`` and
    ``data.inGameID`` (used for the jacket). -> We do NOT need music_db.xml.
  * ``pbs[]`` items carry ``chartID``, ``scoreData.{score,grade,lamp}`` and
    ``timeAchieved`` (Unix milliseconds).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import requests

from vf import calculate_vf

logger = logging.getLogger(__name__)

API_BASE = "https://kamai.tachi.ac/api/v1"

# Tachi rate-limits/409s clients with implausible User-Agents (verified: the
# default urllib UA gets HTTP 403 while a descriptive UA gets HTTP 200).
_HEADERS = {
    "User-Agent": "SDVX-B50-Bot/1.0 (+https://github.com/John-UNOwen/SDVX-B50-Image-Bot)"
}

# Transient statuses worth one retry before giving up.
RETRYABLE_STATUSES = (429, 500, 502, 503, 504)


class TachiError(RuntimeError):
    """Base error communicating with Tachi."""


class UserNotFound(TachiError):
    """The Tachi username does not exist or has no public SDVX data."""


class PrivateProfile(TachiError):
    """The user's profile is private/hidden so scores are not readable."""


def _norm_diff(diff) -> str:
    """Normalise tachi difficulty to the renderer's keys (MAX -> MXM)."""
    return (diff or "EXH").upper().replace("MAX", "MXM")


def _request(url: str, timeout: float, attempts: int = 2) -> requests.Response:
    """GET *url* with the bot UA, retrying once on transient failures.

    Raises :class:`TachiError` when the network stays unreachable.
    """
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, timeout=timeout, headers=_HEADERS)
        except requests.RequestException as exc:
            if attempt < attempts:
                logger.warning("Tachi request failed (attempt %d/%d): %s", attempt, attempts, exc)
                time.sleep(0.5 * attempt)
                continue
            raise TachiError(f"Could not reach Tachi: {exc}") from exc

        if r.status_code in RETRYABLE_STATUSES and attempt < attempts:
            logger.warning(
                "Tachi HTTP %s (attempt %d/%d); retrying",
                r.status_code,
                attempt,
                attempts,
            )
            time.sleep(0.5 * attempt)
            continue
        return r
    raise RuntimeError("unreachable")  # pragma: no cover


def fetch_pbs(username: str):
    """Return ``(pbs, charts_by_chartID)`` for the user.

    Raises :class:`UserNotFound`, :class:`PrivateProfile` or :class:`TachiError`.
    """
    url = f"{API_BASE}/users/{quote(username, safe='')}/games/sdvx/pbs/all"
    logger.info("Tachi GET %s", url)
    t0 = time.monotonic()
    r = _request(url, timeout=30)
    logger.info("Tachi -> HTTP %s (%.2fs)", r.status_code, time.monotonic() - t0)

    if r.status_code == 404:
        raise UserNotFound(username)
    if r.status_code == 429:
        raise TachiError("Tachi is rate-limiting requests; try again in a moment.")
    if r.status_code in (401, 403):
        raise PrivateProfile(username)

    try:
        data = r.json()
    except ValueError as exc:
        raise TachiError(f"Bad response from Tachi (HTTP {r.status_code})") from exc

    if data.get("success") is False:
        raise TachiError(data.get("description") or "Tachi returned an error")

    body = data.get("body") or {}
    pbs = body.get("pbs", [])
    charts = {
        c.get("chartID"): c
        for c in body.get("charts", [])
        if c.get("chartID")
    }
    logger.info("Tachi %s: %d pbs, %d charts", username, len(pbs), len(charts))
    return pbs, charts


def find_user(username: str) -> str:
    """Return the canonical Tachi username if the user exists (light validation).

    Used by /link to confirm the username before storing it. Raises
    :class:`UserNotFound`, :class:`PrivateProfile` or :class:`TachiError`.
    """
    url = f"{API_BASE}/users/{quote(username, safe='')}"
    logger.info("Tachi user lookup: %s", username)
    t0 = time.monotonic()
    r = _request(url, timeout=20)
    logger.info(
        "Tachi lookup %s -> HTTP %s (%.2fs)", username, r.status_code, time.monotonic() - t0
    )
    if r.status_code == 404:
        raise UserNotFound(username)
    if r.status_code == 429:
        raise TachiError("Tachi is rate-limiting requests; try again in a moment.")
    if r.status_code in (401, 403):
        raise PrivateProfile(username)
    try:
        data = r.json()
    except ValueError as exc:
        raise TachiError(f"Bad response from Tachi (HTTP {r.status_code})") from exc
    if data.get("success") is False:
        raise TachiError(data.get("description") or "Tachi returned an error")
    body = data.get("body") or {}
    name = body.get("username") or username
    logger.info("Tachi user %s -> %s", username, name)
    return name


def build_b50(username: str, exceed: bool = False, limit: int = 50):
    """Fetch pbs, compute VF per chart, and return ``(top_rows, total_vf, skipped)``.

    ``top_rows`` are the payload dicts the renderer expects:
      ``{songId, title, diff, level, score, grade, lamp, vf, timeAchieved}``
    """
    logger.info("Building B50 for %s (exceed=%s)", username, exceed)
    pbs, charts = fetch_pbs(username)
    rows: list[dict] = []
    skipped = 0

    for pb in pbs:
        chart = charts.get(pb.get("chartID"))
        if not chart:
            skipped += 1
            continue

        level_num = chart.get("levelNum")
        if level_num is None or float(level_num) <= 0:
            skipped += 1
            continue

        sd = pb.get("scoreData", {})
        score = int(sd.get("score") or 0)
        if score <= 0:
            # A PB without a score is a degenerate entry; otherwise it would
            # appear as a fake 0-VF card for players with fewer than 50 charts.
            skipped += 1
            continue

        grade = (sd.get("grade") or "D").upper()
        lamp = (sd.get("lamp") or "FAILED").upper()

        vf = calculate_vf(level_num, score, grade=grade, lamp=lamp, exceed=exceed)

        rows.append(
            {
                "songId": (chart.get("data") or {}).get("inGameID"),
                "title": (chart.get("song") or {}).get("title") or "???",
                "diff": _norm_diff(chart.get("difficulty")),
                "level": float(level_num),
                "score": score,
                "grade": grade,
                "lamp": lamp,
                "vf": vf,
                "timeAchieved": pb.get("timeAchieved"),
            }
        )

    rows.sort(key=lambda r: r["vf"], reverse=True)
    top = rows[:limit]
    total_vf = sum(r["vf"] for r in top)
    logger.info(
        "B50 %s: %d charts -> top %d, VF %.3f (skipped %d)",
        username,
        len(rows),
        len(top),
        total_vf,
        skipped,
    )
    return top, total_vf, skipped
