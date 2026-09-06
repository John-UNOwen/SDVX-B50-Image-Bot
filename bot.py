"""Discord bot: ``/b50 [username] [mode]``, ``/link <username>``, ``/unlink``.

Run:  set DISCORD_TOKEN=... then  python bot.py   (or set it in ``.env``).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import links
from b50_render.generate import generate_b50_image
from logsetup import setup_logging
from tachi import (
    PrivateProfile,
    TachiError,
    UserNotFound,
    build_b50,
    find_user,
)

logger = logging.getLogger(__name__)

load_dotenv()
setup_logging()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set (set it in .env or the environment).")


class B50Bot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(
            command_prefix="!",
            intents=intents,
            case_insensitive=True,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        await self.tree.sync()


bot = B50Bot()


@bot.tree.command(name="b50", description="Generate your SDVX B50 image from Tachi")
@app_commands.describe(
    username="Your Tachi/Kamaitachi username (optional if you're linked)",
    mode="Which VF version to use",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Nabla (current)", value="nabla"),
        app_commands.Choice(name="Exceed Gear", value="exceed"),
    ]
)
async def b50(
    interaction: discord.Interaction,
    username: str | None = None,
    mode: str = "nabla",
) -> None:
    logger.info(
        "/b50 by %s (%s): username=%r mode=%s",
        interaction.user,
        interaction.user.id,
        username,
        mode,
    )
    # Rendering (jackets + VF) can take tens of seconds; defer so Discord
    # doesn't treat us as unresponsive.
    await interaction.response.defer()

    if not username:
        username = links.get_link(str(interaction.user.id))
        if not username:
            logger.info("/b50: no username and no link for user %s", interaction.user.id)
            await interaction.followup.send(
                "No username given and no link found. "
                "Use `/link <kamaitachi-username>` once, or `/b50 <username>`."
            )
            return

    t0 = time.monotonic()
    try:
        rows, total_vf, skipped = await asyncio.to_thread(
            build_b50, username, exceed=(mode == "exceed")
        )
    except UserNotFound:
        logger.warning("/b50: user not found: %s", username)
        await interaction.followup.send(
            f"Couldn't find a public Tachi user `{username}`."
        )
        return
    except PrivateProfile:
        logger.warning("/b50: private profile: %s", username)
        await interaction.followup.send(
            f"`{username}` exists but their profile is private — scores aren't visible."
        )
        return
    except TachiError as exc:
        logger.error("/b50: tachi error: %s", exc)
        await interaction.followup.send(f"Tachi error: {exc}")
        return

    if not rows:
        logger.warning("/b50: no charts for %s", username)
        await interaction.followup.send(
            f"No SDVX charts found for `{username}`. Check the username spelling."
        )
        return

    payload = {
        "username": username,
        "vf": total_vf,
        "mode": mode,
        "scores": rows,
    }
    try:
        img = await asyncio.to_thread(generate_b50_image, payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("/b50: render failed: %s", exc)
        await interaction.followup.send(f"Image rendering failed: {exc}")
        return

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    ver = "Exceed Gear" if mode == "exceed" else "Nabla"
    note = f" · {ver}" + (f" · skipped {skipped} chart(s)" if skipped else "")
    logger.info(
        "/b50 done for %s: %.3f VF (%d charts, skipped %d) in %.2fs",
        username,
        total_vf,
        len(rows),
        skipped,
        time.monotonic() - t0,
    )
    await interaction.followup.send(
        content=f"**{total_vf:.3f} VF**{note}",
        file=discord.File(buf, filename="b50.png"),
    )


@bot.tree.command(
    name="link", description="Link your Discord account to a Tachi/Kamaitachi username"
)
@app_commands.describe(username="Your Tachi/Kamaitachi username")
async def link(interaction: discord.Interaction, username: str) -> None:
    logger.info(
        "/link by %s (%s) -> %s", interaction.user, interaction.user.id, username
    )
    try:
        canonical = await asyncio.to_thread(find_user, username)
    except UserNotFound:
        logger.warning("/link: user not found: %s", username)
        await interaction.response.send_message(
            f"Couldn't find a Tachi user `{username}`."
        )
        return
    except PrivateProfile:
        logger.warning("/link: private profile: %s", username)
        await interaction.response.send_message(
            f"`{username}` exists but their profile is private — scores aren't visible. "
            "Make it public, then link again."
        )
        return
    except TachiError as exc:
        logger.error("/link: tachi error: %s", exc)
        await interaction.response.send_message(f"Tachi error: {exc}")
        return

    links.set_link(str(interaction.user.id), canonical)
    await interaction.response.send_message(
        f"Linked **{interaction.user.display_name}** → `{canonical}`. "
        "You can now run `/b50` without an argument."
    )


@bot.tree.command(
    name="unlink", description="Unlink your Discord account from your Tachi username"
)
async def unlink(interaction: discord.Interaction) -> None:
    logger.info("/unlink by %s (%s)", interaction.user, interaction.user.id)
    removed = links.unlink(str(interaction.user.id))
    if removed:
        await interaction.response.send_message(
            "Unlinked. Use `/link <username>` to link again."
        )
    else:
        await interaction.response.send_message(
            "You don't have a link to remove. Use `/link <username>` to add one."
        )


bot.run(TOKEN)
