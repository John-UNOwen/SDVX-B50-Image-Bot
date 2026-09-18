#!/usr/bin/env python3
"""Container entrypoint: make the named-volume mount targets appuser-writable,
then drop privileges and exec the bot.

Why this exists
---------------
The bot runs as the non-root `appuser` (uid 1000), but its two writable paths
(`/app/data` and `/app/b50_render/.jacket_cache`) are named-volume mount
targets. Docker only copies the image directory's ownership into a named volume
the FIRST time it is populated; that one-time copy is NOT a reliable guarantee
across hosts (user-namespace remapping can land the volume with a host uid that
differs from the container's uid 1000) and does NOT repair a volume that was
reused after being populated as root.

So at every boot we run as container root, re-own the two mount targets
(recursively, but only when the target is not already appuser-owned — the
steady-state case — to keep restarts cheap), then drop privileges with the
standard-library `os` module and exec the bot. Because this happens inside the
container's own user namespace, uid 1000 is exactly what `appuser` sees, and it
works regardless of which host uid originally populated the volume. Python's
`os` module is the only thing needed (it is the app runtime), so no system
binary such as `su`/`setpriv`/PAM is required.
"""
from __future__ import annotations

import os
import sys

try:  # POSIX-only; never imported at runtime on the Linux container.
    import pwd  # noqa: PLC0415
except ImportError:  # pragma: no cover — Windows/dev-only, so tests can import on any host
    pwd = None

APPUSER = "appuser"
MOUNTS = ("/app/data", "/app/b50_render/.jacket_cache")


def _ensure_owned(path: str, uid: int, gid: int) -> None:
    """Recursively chown `path` to (uid, gid).

    The recursion is the repair path for a reused / root-populated volume: it
    only descends when the target is not already appuser-owned (the common,
    cheap case at steady state).
    """
    import logging
    st = os.stat(path)
    os.chown(path, uid, gid)
    if st.st_uid == uid and st.st_gid == gid:
        return  # already ours; do not walk thousands of cache files
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            os.lchown(os.path.join(dirpath, name), uid, gid)
    logging.info("re-owned %s for %s", path, APPUSER)


def main() -> int:
    if pwd is None:  # pragma: no cover — non-POSIX host
        print("entrypoint: requires POSIX (pwd module)", file=sys.stderr)
        return 1
    try:
        pw = pwd.getpwnam(APPUSER)
        uid, gid = pw.pw_uid, pw.pw_gid
    except (KeyError, OSError) as exc:
        print(f"entrypoint: user {APPUSER!r} not found: {exc}", file=sys.stderr)
        return 1

    for mount in MOUNTS:
        if not os.path.exists(mount):
            print(f"entrypoint: mount target {mount} missing (volume not mounted?)",
                  file=sys.stderr)
            return 1
        _ensure_owned(mount, uid, gid)

    # Drop privileges to appuser. Already non-root (e.g. a user ran the image
    # with `--user`) is fine: setuid fails and we just continue as that user.
    try:
        if uid != os.geteuid():
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
    except OSError as exc:
        print(f"entrypoint: could not drop to {APPUSER}: {exc}", file=sys.stderr)
        return 1

    os.chdir("/app")
    os.execv(sys.executable, [sys.executable, "bot.py"])
    return 2  # pragma: no cover — execv replaces the process


if __name__ == "__main__":
    sys.exit(main())