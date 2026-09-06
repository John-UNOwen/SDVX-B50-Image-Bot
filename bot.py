"""Discord bot: ``/b50 <username> [mode]`` -> SDVX B50 image.

Run:  set DISCORD_TOKEN=... then  python bot.py   (or set it in ``.env``).
"""

from __future__ import annotations

import asyncio
import io
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from b50_render.generate import generate_b50_image
from tachi import PrivateProfile, TachiError, UserNotFound, build_b50

load_dotenv()

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
    username="Your Tachi/Kamaitachi username",
    mode="Which VF version to use",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Nabla (current)", value="nabla"),
        app_commands.Choice(name="Exceed Gear", value="exceed"),
    ]
)
async def b50(
    interaction: discord.Interaction, username: str, mode: str = "nabla"
) -> None:
    # Rendering (jackets + VF) can take tens of seconds; defer so Discord
    # doesn't treat us as unresponsive.
    await interaction.response.defer()

    try:
        rows, total_vf, skipped = await asyncio.to_thread(
            build_b50, username, exceed=(mode == "exceed")
        )
    except UserNotFound:
        await interaction.followup.send(
            f"Couldn't find a public Tachi user `{username}`."
        )
        return
    except PrivateProfile:
        await interaction.followup.send(
            f"`{username}` exists but their profile is private — scores aren't visible."
        )
        return
    except TachiError as exc:
        await interaction.followup.send(f"Tachi error: {exc}")
        return

    if not rows:
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
        await interaction.followup.send(f"Image rendering failed: {exc}")
        return

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    ver = "Exceed Gear" if mode == "exceed" else "Nabla"
    note = f" · {ver}" + (f" · skipped {skipped} chart(s)" if skipped else "")
    await interaction.followup.send(
        content=f"**{total_vf:.3f} VF**{note}",
        file=discord.File(buf, filename="b50.png"),
    )


bot.run(TOKEN)
