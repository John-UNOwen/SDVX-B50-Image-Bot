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

# How long we wait for Tachi before falling back to a public defer. Must stay
# under Discord's 3-second interaction acknowledgment window.
BUILD_TIMEOUT = 2.5  # seconds

# At most this many images render at once (jackets + Pillow work is
# CPU/network heavy, so concurrent bursts shouldn't stack up).
RENDER_SEM = asyncio.Semaphore(4)


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


async def _send_error(
    interaction: discord.Interaction, message: str, *, deferred: bool
) -> None:
    """Send a user-facing error.

    *deferred* is True when the interaction was already acknowledged with a
    public defer: Discord ignores the ephemeral flag on followups then, which
    only happens when Tachi was too slow for the 3s acknowledgment window.
    """
    if deferred:
        await interaction.followup.send(message)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.error
async def on_tree_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Global handler: friendly cooldown message + catch-all so an unhandled
    error never leaves an interaction silently unanswered."""
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Slow down — try again in {error.retry_after:.0f}s.", ephemeral=True
        )
        return
    logger.error("Unhandled command error: %s", error, exc_info=True)
    try:
        await interaction.response.send_message(
            "Something went wrong. Please try again.", ephemeral=True
        )
    except discord.HTTPException:
        pass  # already responded / impossible to respond; logs have the error


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
@app_commands.checks.cooldown(1, 10.0)  # per user; lookups are expensive
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

    # Fetch BEFORE deferring so user/data errors can be the *initial* response
    # (Discord ignores the ephemeral flag on followups after a public defer).
    # If Tachi is too slow for the 3s window, fall back to a public defer and
    # finish in the background — rare, and errors then have to be public.
    # ``shield`` keeps the original fetch alive so the slow path reuses it
    # instead of issuing a second request.
    t0 = time.monotonic()
    fast = True
    task = asyncio.create_task(
        asyncio.to_thread(build_b50, username, exceed=(mode == "exceed"))
    )
    try:
        rows, total_vf, skipped = await asyncio.wait_for(
            asyncio.shield(task), timeout=BUILD_TIMEOUT
        )
    except asyncio.TimeoutError:
        fast = False
        logger.warning(
            "/b50: Tachi fetch over %.1fs for %s; deferring publicly",
            BUILD_TIMEOUT,
            username,
        )
        await interaction.response.defer()
        try:
            rows, total_vf, skipped = await task
        except UserNotFound:
            logger.warning("/b50: no public sdvx data for %s", username)
            await _send_error(
                interaction,
                f"Couldn't find public SDVX scores for `{username}`. "
                "Check the username spelling or profile visibility.",
                deferred=True,
            )
            return
        except PrivateProfile:
            logger.warning("/b50: private profile: %s", username)
            await _send_error(
                interaction,
                f"`{username}` exists but their profile is private — scores aren't visible.",
                deferred=True,
            )
            return
        except TachiError as exc:
            logger.error("/b50: tachi error: %s", exc)
            await _send_error(interaction, f"Tachi error: {exc}", deferred=True)
            return
    except UserNotFound:
        logger.warning("/b50: no public sdvx data for %s", username)
        await _send_error(
            interaction,
            f"Couldn't find public SDVX scores for `{username}`. "
            "Check the username spelling or profile visibility.",
            deferred=False,
        )
        return
    except PrivateProfile:
        logger.warning("/b50: private profile: %s", username)
        await _send_error(
            interaction,
            f"`{username}` exists but their profile is private — scores aren't visible.",
            deferred=False,
        )
        return
    except TachiError as exc:
        logger.error("/b50: tachi error: %s", exc)
        await _send_error(interaction, f"Tachi error: {exc}", deferred=False)
        return

    if not rows:
        logger.warning("/b50: no charts for %s", username)
        await _send_error(
            interaction,
            f"No SDVX charts found for `{username}`. Check the username spelling.",
            deferred=not fast,
        )
        return

    # Data is ready (fast path: inside Discord's 3s window). Now defer for the
    # slow render (jackets + image); the result stays public.
    if fast:
        await interaction.response.defer()

    payload = {
        "username": username,
        "vf": total_vf,
        "mode": mode,
        "scores": rows,
    }
    try:
        async with RENDER_SEM:
            img = await asyncio.to_thread(generate_b50_image, payload)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
    except Exception as exc:  # noqa: BLE001
        logger.error("/b50: render failed: %s", exc, exc_info=True)
        # After a public defer we cannot hide followups; keep the message
        # neutral and leave the details in the logs.
        await interaction.followup.send(
            "Something went wrong while rendering the image. Please try again."
        )
        return

    logger.info(
        "/b50 done for %s: %.3f VF (%d charts, skipped %d, mode=%s) in %.2fs",
        username,
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

    if not links.set_link(str(interaction.user.id), canonical):
        logger.error("/link: could not store link for user %s", interaction.user.id)
        await interaction.response.send_message(
            "Couldn't save the link (storage problem). Try again later.",
            ephemeral=True,
        )
        return

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
    if removed is None:
        logger.error("/unlink: link store error for user %s", interaction.user.id)
        await interaction.response.send_message(
            "Couldn't read the link store. Try again later.", ephemeral=True
        )
        return
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
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


bot.run(TOKEN)
