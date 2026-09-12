"""Export every Journal Club channel to one CSV for analysis.

    python -m src.export

Writes journal-club-export.csv in the current directory; set EXPORT_PATH to put
it elsewhere. Stop the bot first if it's running — not required, but it keeps
new messages from landing mid-export.

Read-only by construction: this connects, reads history, and disconnects. It
never posts, never touches the database, and never starts the scheduler.

One row per message, with a `channel` column, so a pivot table gets you
per-channel and per-speaker comparisons without any further wrangling.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys

import discord

from .config import CHANNEL_NAMES, Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

FIELDS = [
    "timestamp",
    "channel",
    "speaker",
    "speaker_kind",
    "message_id",
    "reply_to",
    "reactions",
    "chars",
    "content",
]


def _speaker_kind(msg: discord.Message) -> str:
    """Models post through webhooks; the bot posts announcements as itself."""
    if msg.webhook_id:
        return "model"
    if msg.author.bot:
        return "bot"
    return "human"


async def _export(config: Config, out_path: str) -> None:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    client = discord.Client(intents=intents)

    # on_ready fires again on reconnect; without this a blip mid-export would
    # restart it and truncate the file it had already begun writing.
    started = False

    @client.event
    async def on_ready() -> None:
        nonlocal started
        if started:
            return
        started = True
        try:
            guild = client.get_guild(config.guild_id)
            if guild is None:
                log.error("Could not find guild %s", config.guild_id)
                return

            category = discord.utils.get(
                guild.categories, name=config.discord_category
            )
            if category is None:
                log.error(
                    "Could not find the category %r. Set DISCORD_CATEGORY if it "
                    "has been renamed.",
                    config.discord_category,
                )
                return

            total = 0
            with open(out_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()

                for name in CHANNEL_NAMES:
                    channel = discord.utils.get(
                        guild.text_channels, name=name, category=category
                    )
                    if channel is None:
                        log.warning("No #%s under %r — skipping", name, category.name)
                        continue

                    count = 0
                    # oldest_first so the CSV reads in conversation order.
                    async for msg in channel.history(limit=None, oldest_first=True):
                        writer.writerow(
                            {
                                "timestamp": msg.created_at.isoformat(),
                                "channel": name,
                                "speaker": msg.author.display_name
                                or msg.author.name,
                                "speaker_kind": _speaker_kind(msg),
                                "message_id": str(msg.id),
                                "reply_to": (
                                    str(msg.reference.message_id)
                                    if msg.reference
                                    else ""
                                ),
                                "reactions": " ".join(
                                    f"{r.emoji}x{r.count}" for r in msg.reactions
                                ),
                                "chars": len(msg.content),
                                "content": msg.content,
                            }
                        )
                        count += 1

                    total += count
                    log.info("#%-14s %6d messages", name, count)

            log.info("Wrote %d rows to %s", total, out_path)
        except Exception:
            log.exception("Export failed")
        finally:
            await client.close()

    await client.start(config.discord_token)


def main() -> None:
    try:
        config = Config()
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        print("Copy .env.example to .env and fill in your keys.")
        sys.exit(1)

    out_path = os.environ.get("EXPORT_PATH", "journal-club-export.csv")
    asyncio.run(_export(config, out_path))


if __name__ == "__main__":
    main()
