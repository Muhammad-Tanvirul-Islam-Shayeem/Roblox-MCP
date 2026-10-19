from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db

MAX_TIMEOUT_MINUTES = 28 * 24 * 60  # Discord's hard limit is 28 days
NO_REASON = "No reason provided"


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def hierarchy_error(interaction: discord.Interaction, target: discord.Member) -> str | None:
        """Return why the invoker/bot may not act on `target`, or None if allowed."""
        guild = interaction.guild
        author = interaction.user
        if target.id == author.id:
            return "You can't do that to yourself."
        if target.id == guild.me.id:
            return "I won't do that to myself."
        if target.id == guild.owner_id:
            return "You can't moderate the server owner."
        if author.id != guild.owner_id and target.top_role >= author.top_role:
            return "That member's highest role is equal to or above yours."
        if target.top_role >= guild.me.top_role:
            return "That member's highest role is equal to or above mine."
        return None

    async def log_action(
        self,
        guild: discord.Guild,
        action: str,
        moderator: discord.abc.User,
        target: discord.abc.User | discord.Object,
        reason: str,
        colour: discord.Colour = discord.Colour.orange(),
        extra: str | None = None,
    ) -> None:
        channel_id = await db.get_log_channel(guild.id)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        embed = discord.Embed(title=action, colour=colour, timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"<@{target.id}> (`{target.id}`)", inline=False)
        embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=False)
        embed.add_field(name="Reason", value=reason[:1024], inline=False)
        if extra:
            embed.add_field(name="Details", value=extra, inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass  # Missing access to the log channel shouldn't break the command.

    @staticmethod
    async def dm_user(user: discord.abc.User, guild: discord.Guild, text: str, reason: str) -> None:
        try:
            await user.send(f"{text} **{guild.name}**.\nReason: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            pass  # User has DMs closed.

    # ---- kick / ban / unban ------------------------------------------------

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Why they're being kicked")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = NO_REASON):
        if error := self.hierarchy_error(interaction, member):
            return await interaction.response.send_message(error, ephemeral=True)
        await self.dm_user(member, interaction.guild, "You were kicked from", reason)
        await member.kick(reason=f"{interaction.user} ({interaction.user.id}): {reason}")
        await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}")
        await self.log_action(interaction.guild, "Member kicked", interaction.user, member, reason)

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        member="Member to ban",
        reason="Why they're being banned",
        delete_days="Days of their messages to delete (0-7)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = NO_REASON,
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ):
        if error := self.hierarchy_error(interaction, member):
            return await interaction.response.send_message(error, ephemeral=True)
        await self.dm_user(member, interaction.guild, "You were banned from", reason)
        await member.ban(
            reason=f"{interaction.user} ({interaction.user.id}): {reason}",
            delete_message_seconds=delete_days * 86400,
        )
        await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}")
        await self.log_action(
            interaction.guild, "Member banned", interaction.user, member, reason, discord.Colour.red()
        )

    @app_commands.command(name="unban", description="Unban a user by their ID.")
    @app_commands.describe(user_id="ID of the banned user", reason="Why they're being unbanned")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = NO_REASON):
        if not user_id.isdigit():
            return await interaction.response.send_message("That isn't a valid user ID.", ephemeral=True)
        target = discord.Object(id=int(user_id))
        try:
            await interaction.guild.unban(target, reason=f"{interaction.user} ({interaction.user.id}): {reason}")
        except discord.NotFound:
            return await interaction.response.send_message("That user isn't banned.", ephemeral=True)
        await interaction.response.send_message(f"✅ Unbanned <@{target.id}>.")
        await self.log_action(
            interaction.guild, "Member unbanned", interaction.user, target, reason, discord.Colour.green()
        )

    # ---- timeout -----------------------------------------------------------

    @app_commands.command(name="timeout", description="Temporarily mute a member.")
    @app_commands.describe(member="Member to time out", minutes="Duration in minutes", reason="Why")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, MAX_TIMEOUT_MINUTES],
        reason: str = NO_REASON,
    ):
        if error := self.hierarchy_error(interaction, member):
            return await interaction.response.send_message(error, ephemeral=True)
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await member.timeout(until, reason=f"{interaction.user} ({interaction.user.id}): {reason}")
        stamp = discord.utils.format_dt(until, "R")
        await interaction.response.send_message(f"🔇 Timed out {member.mention} until {stamp}. Reason: {reason}")
        await self.log_action(
            interaction.guild, "Member timed out", interaction.user, member, reason, extra=f"Expires {stamp}"
        )

    @app_commands.command(name="untimeout", description="Remove a member's timeout.")
    @app_commands.describe(member="Member to un-timeout", reason="Why")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = NO_REASON):
        if error := self.hierarchy_error(interaction, member):
            return await interaction.response.send_message(error, ephemeral=True)
        await member.timeout(None, reason=f"{interaction.user} ({interaction.user.id}): {reason}")
        await interaction.response.send_message(f"🔊 Removed timeout from {member.mention}.")
        await self.log_action(
            interaction.guild, "Timeout removed", interaction.user, member, reason, discord.Colour.green()
        )

    # ---- warnings ----------------------------------------------------------

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(member="Member to warn", reason="Why they're being warned")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if error := self.hierarchy_error(interaction, member):
            return await interaction.response.send_message(error, ephemeral=True)
        warn_id = await db.add_warning(interaction.guild.id, member.id, interaction.user.id, reason)
        total = len(await db.get_warnings(interaction.guild.id, member.id))
        await self.dm_user(member, interaction.guild, "You were warned in", reason)
        await interaction.response.send_message(
            f"⚠️ Warned {member.mention} (warning #{warn_id}, {total} total). Reason: {reason}"
        )
        await self.log_action(
            interaction.guild, "Member warned", interaction.user, member, reason, extra=f"Total warnings: {total}"
        )

    @app_commands.command(name="warnings", description="List a member's warnings.")
    @app_commands.describe(member="Member to look up")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        rows = await db.get_warnings(interaction.guild.id, member.id)
        if not rows:
            return await interaction.response.send_message(f"{member.mention} has no warnings.", ephemeral=True)
        lines = [
            f"**#{r['id']}** • <t:{r['created_at']}:d> • by <@{r['moderator_id']}> — {r['reason']}"
            for r in rows[-10:]
        ]
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description="\n".join(lines),
            colour=discord.Colour.orange(),
        )
        embed.set_footer(text=f"{len(rows)} total" + (" (showing latest 10)" if len(rows) > 10 else ""))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Delete all of a member's warnings.")
    @app_commands.describe(member="Member whose warnings to clear")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        removed = await db.clear_warnings(interaction.guild.id, member.id)
        await interaction.response.send_message(f"🧹 Cleared {removed} warning(s) for {member.mention}.")
        await self.log_action(
            interaction.guild,
            "Warnings cleared",
            interaction.user,
            member,
            NO_REASON,
            discord.Colour.green(),
            extra=f"{removed} removed",
        )

    # ---- purge / settings --------------------------------------------------

    @app_commands.command(name="purge", description="Bulk-delete recent messages in this channel.")
    @app_commands.describe(amount="How many messages to delete (1-100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} message(s).", ephemeral=True)
        await self.log_action(
            interaction.guild,
            "Messages purged",
            interaction.user,
            interaction.user,
            NO_REASON,
            extra=f"{len(deleted)} in {interaction.channel.mention}",
        )

    @app_commands.command(name="setlogchannel", description="Choose where moderation actions are logged.")
    @app_commands.describe(channel="Channel to send mod logs to")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setlogchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        perms = channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                f"I need **Send Messages** and **Embed Links** in {channel.mention}.", ephemeral=True
            )
        await db.set_log_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"📝 Mod logs will be sent to {channel.mention}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
