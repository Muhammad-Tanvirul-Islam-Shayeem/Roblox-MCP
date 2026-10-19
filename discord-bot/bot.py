import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("modbot")


class ModBot(commands.Bot):
    def __init__(self) -> None:
        # Slash commands need no privileged intents.
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())

    async def setup_hook(self) -> None:
        await db.init()
        await self.load_extension("cogs.moderation")

        # With DEV_GUILD_ID set, commands sync to that server instantly instead of
        # taking up to an hour to propagate globally.
        dev_guild = os.getenv("DEV_GUILD_ID")
        if dev_guild:
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to dev guild %s", dev_guild)
        else:
            await self.tree.sync()
            log.info("Synced commands globally")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id)


bot = ModBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        msg = "You don't have permission to use this command."
    elif isinstance(error, app_commands.BotMissingPermissions):
        needed = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
        msg = f"I'm missing permissions: {needed}."
    elif isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
        msg = "Discord refused that action. Check my role position and permissions."
    else:
        log.exception("Unhandled command error", exc_info=error)
        msg = "Something went wrong running that command."

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
