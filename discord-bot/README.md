# Discord Moderation Bot

A small moderation bot built with [discord.py](https://discordpy.readthedocs.io/). It is separate from the Roblox MCP server in the rest of this repo.

## Commands

| Command | Permission needed | What it does |
| --- | --- | --- |
| `/kick member [reason]` | Kick Members | Kick a member |
| `/ban member [reason] [delete_days]` | Ban Members | Ban a member, optionally deleting 0-7 days of messages |
| `/unban user_id [reason]` | Ban Members | Unban a user by ID |
| `/timeout member minutes [reason]` | Moderate Members | Timeout a member (up to 28 days) |
| `/untimeout member [reason]` | Moderate Members | Remove a timeout |
| `/warn member reason` | Moderate Members | Record a warning and DM the member |
| `/warnings member` | Moderate Members | Show a member's latest warnings |
| `/clearwarnings member` | Moderate Members | Delete all of a member's warnings |
| `/purge amount` | Manage Messages | Delete 1-100 recent messages in the channel |
| `/setlogchannel channel` | Manage Server | Choose the channel for mod-action logs |

Moderators can't act on themselves, the server owner, or anyone whose top role is equal to or above their own (or the bot's).

## Setup

1. Create an application at <https://discord.com/developers/applications>, add a **Bot**, and copy its token.
2. Invite it with the `bot` and `applications.commands` scopes and these permissions: Kick Members, Ban Members, Moderate Members, Manage Messages, Read Message History, Send Messages, Embed Links.
3. Put the bot's role **above** the roles it should be able to moderate.
4. Install and run:

```bash
cd discord-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set DISCORD_TOKEN
python bot.py
```

Set `DEV_GUILD_ID` in `.env` to sync commands to one server instantly while developing. Without it, commands sync globally, which can take up to an hour to show up.

Warnings and log-channel settings are stored in `moderation.db` (SQLite) next to the bot. No privileged intents are required.

Never commit your `.env` file or token. If a token leaks, reset it in the developer portal.
