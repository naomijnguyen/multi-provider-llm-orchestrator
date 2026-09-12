"""Entry point for Journal Club — the AI journal club Discord bot."""

from __future__ import annotations

import logging
import os
import sys

from discord.ext import commands

from .bot import BookClubBot
from .config import Config
from .scheduler import describe, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    config = Config()

    # The bot needs Discord; the experiment does not, which is why Config no
    # longer refuses to build without these. Validate here instead.
    if not config.discord_token:
        print("DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)
    if not config.guild_id:
        raw = os.environ.get("DISCORD_GUILD_ID", "")
        if raw.strip():
            print(f"DISCORD_GUILD_ID is not a plain integer: {raw!r}")
            print("A Discord guild id is 18-19 digits with no spaces.")
        else:
            print("DISCORD_GUILD_ID is not set.")
        sys.exit(1)

    if config.owner_id is None:
        sys.exit("DISCORD_OWNER_ID must be configured before starting the bot.")

    bot = BookClubBot(config)

    def _is_owner(ctx: commands.Context) -> bool:
        """Every command spends provider tokens, so gate them on the owner."""
        return (config.owner_id is not None
                and ctx.author.id == config.owner_id
                and ctx.guild is not None
                and ctx.guild.id == config.guild_id)

    @bot.command(name="scrape")
    @commands.check(_is_owner)
    async def cmd_scrape(ctx: commands.Context) -> None:
        """Manually trigger a scrape + discussion cycle."""
        await ctx.send("🔍 Scraping LessWrong for new posts...")
        await bot.process_new_posts()
        await ctx.send("✅ Done!")

    @bot.command(name="gossip")
    @commands.check(_is_owner)
    async def cmd_gossip(ctx: commands.Context) -> None:
        """Manually trigger a gossip round."""
        await ctx.send("💬 Starting gossip round...")
        await bot._generate_gossip()

    @bot.command(name="club")
    @commands.check(_is_owner)
    async def cmd_club(ctx: commands.Context, action: str = "status") -> None:
        """!club start | stop | status — control the scheduled runs."""
        action = action.lower()
        if action == "start":
            started = start_scheduler(bot)
            await ctx.send("▶️ Club started." if started else "Already running.")
        elif action == "stop":
            await ctx.send("⏹️ Club stopped." if stop_scheduler(bot) else "Not running.")
        else:
            await ctx.send(describe(bot))

    @bot.command(name="status")
    @commands.check(_is_owner)
    async def cmd_status(ctx: commands.Context) -> None:
        """Show bot status."""
        from . import db
        posts = db.get_recent_posts(config.db_path, limit=5)
        if not posts:
            await ctx.send("No posts yet. Run `!scrape` to get started.")
            return
        lines = ["**Recent posts:**"]
        for p in posts:
            lines.append(f"• [{p['status']}] {p['title']}")
        await ctx.send("\n".join(lines))

    # Connecting never starts paid scheduled work.
    original_on_ready = bot.on_ready

    async def on_ready_with_scheduler() -> None:
        await original_on_ready()
        log.info("Journal Club connected. Use !club start to enable scheduled work.")

    bot.on_ready = on_ready_with_scheduler  # type: ignore[assignment]

    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
