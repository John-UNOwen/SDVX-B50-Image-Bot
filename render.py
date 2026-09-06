"""CLI test driver (no Discord): ``python render.py <username> [-o out.png] [--exceed]``.

Lets you verify the full fetch -> VF -> PNG pipeline locally before wiring up
the bot, and produces a preview to compare against tachisdvxdata.com/top50.
"""

from __future__ import annotations

import argparse
import sys

from b50_render.generate import generate_b50_image
from tachi import TachiError, build_b50


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an SDVX B50 image")
    parser.add_argument("username", help="Tachi/Kamaitachi username")
    parser.add_argument("-o", "--out", default="b50.png", help="output PNG (default b50.png)")
    parser.add_argument("--exceed", action="store_true", help="use Exceed Gear VF")
    args = parser.parse_args()

    try:
        rows, total_vf, skipped = build_b50(args.username, exceed=args.exceed)
    except TachiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not rows:
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
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
