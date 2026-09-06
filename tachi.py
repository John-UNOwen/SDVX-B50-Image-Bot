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
    ``timeAchieved``.
"""

from __future__ import annotations

import requests

from vf import calculate_vf

API_BASE = "https://kamai.tachi.ac/api/v1"


class TachiError(RuntimeError):
    """Base error communicating with Tachi."""


class UserNotFound(TachiError):
    """The Tachi username does not exist or has no public SDVX data."""


class PrivateProfile(TachiError):
    """The user's profile is private/hidden so scores are not readable."""


def _norm_diff(diff) -> str:
    """Normalise tachi difficulty to the renderer's keys (MAX -> MXM)."""
    return (diff or "EXH").upper().replace("MAX", "MXM")


def fetch_pbs(username: str):
    """Return ``(pbs, charts_by_chartID)`` for the user.

    Raises :class:`UserNotFound`, :class:`PrivateProfile` or :class:`TachiError`.
    """
    url = f"{API_BASE}/users/{username}/games/sdvx/pbs/all"
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        raise TachiError(f"Could not reach Tachi: {exc}") from exc

    if r.status_code == 404:
        raise UserNotFound(username)
    if r.status_code in (401, 403):
        raise PrivateProfile(username)

    try:
        data = r.json()
    except ValueError as exc:
        raise TachiError(f"Bad response from Tachi (HTTP {r.status_code})") from exc

    if data.get("success") is False:
        raise TachiError(data.get("description") or "Tachi returned an error")

    body = data.get("body", {})
    pbs = body.get("pbs", [])
    charts = {
        c.get("chartID"): c
        for c in body.get("charts", [])
        if c.get("chartID")
    }
    return pbs, charts


def build_b50(username: str, exceed: bool = False, limit: int = 50):
    """Fetch pbs, compute VF per chart, and return ``(top_rows, total_vf, skipped)``.

    ``top_rows`` are the payload dicts the renderer expects:
      ``{songId, title, diff, level, score, grade, lamp, vf, timeAchieved}``
    """
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
    return top, total_vf, skipped
