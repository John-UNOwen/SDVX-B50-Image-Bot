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
import stats
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
        # Global sync — works in DMs and every server, but Discord can take
        # up to ~1 hour to propagate the commands to clients.
        try:
            await self.tree.sync()
            logger.info("Slash command tree synced (global)")
        except Exception as exc:  # noqa: BLE001
            # A sync failure must not stop the bot from coming online.
            logger.error("Slash command tree sync failed: %s", exc)

        # Optional instant per-guild sync (GUILD_ID in .env): commands show up
        # immediately in that server.
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            try:
                guild = await self.fetch_guild(int(guild_id))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("Slash command tree synced to guild %s", guild_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Guild sync failed (GUILD_ID=%s): %s", guild_id, exc)

    async def on_ready(self) -> None:
        logger.info("Bot online as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="/b50"
            ),
        )


bot = B50Bot()


@bot.tree.command(name="b50", description="Generate your SDVX B50 image from Tachi")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
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

    if not username:
        username = links.get_link(str(interaction.user.id))
        if not username:
            logger.info("/b50: no username and no link for user %s", interaction.user.id)
            stats.record("b50", user_id=str(interaction.user.id), mode=mode, status="no-link")
            await interaction.response.send_message(
                "No username given and no link found. "
                "Use `/link <kamaitachi-username>` once, or `/b50 <username>`.",
                ephemeral=True,
            )
            return

    stats.record("b50", user_id=str(interaction.user.id), mode=mode, target=username)

    # Validate the Tachi user BEFORE deferring: error replies can then use a
    # true ephemeral *initial* response. (Discord ignores ephemeral flags on
    # followups when the deferred response was public.)
    try:
        canonical = await asyncio.to_thread(find_user, username)
    except UserNotFound:
        logger.warning("/b50: user not found: %s", username)
        await interaction.response.send_message(
            f"Couldn't find a public Tachi user `{username}`.", ephemeral=True
        )
        return
    except PrivateProfile:
        logger.warning("/b50: private profile: %s", username)
        await interaction.response.send_message(
            f"`{username}` exists but their profile is private — scores aren't visible.",
            ephemeral=True,
        )
        return
    except TachiError as exc:
        logger.error("/b50: tachi error: %s", exc)
        await interaction.response.send_message(f"Tachi error: {exc}", ephemeral=True)
        return

    # Rendering (jackets + VF) can take tens of seconds; defer so Discord
    # doesn't treat us as unresponsive. The result stays public.
    await interaction.response.defer()

    t0 = time.monotonic()
    try:
        rows, total_vf, skipped = await asyncio.to_thread(
            build_b50, canonical, exceed=(mode == "exceed")
        )
    except UserNotFound:
        logger.warning("/b50: user not found (after validation): %s", canonical)
        await interaction.followup.send(
            f"Couldn't find a public Tachi user `{canonical}`.", ephemeral=True
        )
        return
    except PrivateProfile:
        logger.warning("/b50: private profile (after validation): %s", canonical)
        await interaction.followup.send(
            f"`{canonical}` exists but their profile is private — scores aren't visible.",
            ephemeral=True,
        )
        return
    except TachiError as exc:
        logger.error("/b50: tachi error: %s", exc)
        await interaction.followup.send(f"Tachi error: {exc}", ephemeral=True)
        return

    if not rows:
        logger.warning("/b50: no charts for %s", canonical)
        await interaction.followup.send(
            f"No SDVX charts found for `{canonical}`. Check the username spelling.",
            ephemeral=True,
        )
        return

    payload = {
        "username": canonical,
        "vf": total_vf,
        "mode": mode,
        "scores": rows,
    }
    try:
        img = await asyncio.to_thread(generate_b50_image, payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("/b50: render failed: %s", exc)
        await interaction.followup.send(f"Image rendering failed: {exc}", ephemeral=True)
        return

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    logger.info(
        "/b50 done for %s: %.3f VF (%d charts, skipped %d, mode=%s) in %.2fs",
        canonical,
        total_vf,
        len(rows),
        skipped,
        mode,
        time.monotonic() - t0,
    )
    # The B50 result stays public so players can share it; the image itself
    # shows the total VF, so no text message is sent.
    await interaction.followup.send(file=discord.File(buf, filename="b50.png"))


@bot.tree.command(
    name="link", description="Link your Discord account to a Tachi/Kamaitachi username"
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(username="Your Tachi/Kamaitachi username")
async def link(interaction: discord.Interaction, username: str) -> None:
    logger.info(
        "/link by %s (%s) -> %s", interaction.user, interaction.user.id, username
    )
    stats.record("link", user_id=str(interaction.user.id), target=username)
    try:
        canonical = await asyncio.to_thread(find_user, username)
    except UserNotFound:
        logger.warning("/link: user not found: %s", username)
        await interaction.response.send_message(
            f"Couldn't find a Tachi user `{username}`.", ephemeral=True
        )
        return
    except PrivateProfile:
        logger.warning("/link: private profile: %s", username)
        await interaction.response.send_message(
            f"`{username}` exists but their profile is private — scores aren't visible. "
            "Make it public, then link again.",
            ephemeral=True,
        )
        return
    except TachiError as exc:
        logger.error("/link: tachi error: %s", exc)
        await interaction.response.send_message(
            f"Tachi error: {exc}", ephemeral=True
        )
        return

    links.set_link(str(interaction.user.id), canonical)
    await interaction.response.send_message(
        f"Linked **{interaction.user.display_name}** → `{canonical}`. "
        "You can now run `/b50` without an argument.",
        ephemeral=True,
    )


@bot.tree.command(
    name="unlink", description="Unlink your Discord account from your Tachi username"
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def unlink(interaction: discord.Interaction) -> None:
    logger.info("/unlink by %s (%s)", interaction.user, interaction.user.id)
    stats.record("unlink", user_id=str(interaction.user.id))
    removed = links.unlink(str(interaction.user.id))
    if removed:
        await interaction.response.send_message(
            "Unlinked. Use `/link <username>` to link again.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "You don't have a link to remove. Use `/link <username>` to add one.",
            ephemeral=True,
        )


@bot.tree.command(name="stats", description="Show bot query statistics")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def stats_cmd(interaction: discord.Interaction) -> None:
    s = stats.summary()
    lines = [f"**Total queries: {s['total']}** (last 24h: {s['today']})"]
    for cmd, mode, count in s["by_type"]:
        label = cmd if not mode else f"{cmd} ({mode})"
        lines.append(f"• {label}: **{count}**")
    await interaction.response.send_message("\n".join(lines))


bot.run(TOKEN)
