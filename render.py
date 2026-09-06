"""CLI test driver (no Discord): ``python render.py <username> [-o out.png] [--exceed]``.

Lets you verify the full fetch -> VF -> PNG pipeline locally before wiring up
the bot, and produces a preview to compare against tachisdvxdata.com/top50.
"""

from __future__ import annotations

import argparse
import logging
import sys

from b50_render.generate import generate_b50_image
from logsetup import setup_logging
from tachi import TachiError, build_b50

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Render an SDVX B50 image")
    parser.add_argument("username", help="Tachi/Kamaitachi username")
    parser.add_argument("-o", "--out", default="b50.png", help="output PNG (default b50.png)")
    parser.add_argument("--exceed", action="store_true", help="use Exceed Gear VF")
    args = parser.parse_args()

    try:
        rows, total_vf, skipped = build_b50(args.username, exceed=args.exceed)
    except TachiError as exc:
        logger.error("render failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not rows:
        logger.warning("no charts found for %s", args.username)
        print("no charts found", file=sys.stderr)
        return 1

    mode = "exceed" if args.exceed else "nabla"
    img = generate_b50_image(
        {"username": args.username, "vf": total_vf, "mode": mode, "scores": rows}
    )
    img.save(args.out)

    msg = f"wrote {args.out} · {total_vf:.3f} VF"
    if skipped:
        msg += f" · skipped {skipped} chart(s)"
    logger.info(msg)
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
