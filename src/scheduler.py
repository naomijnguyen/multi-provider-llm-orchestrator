"""Scheduling for the periodic scrape/discuss run and the gossip run.

`start_scheduler` and `stop_scheduler` are mirrors. The bot holds exactly one
scheduler on `bot.scheduler`, and both are safe to call repeatedly — starting an
already-running club is a no-op, not a second scheduler.

Driving this from `!club start` / `!club stop` means the club can be halted
without killing the process, which matters because every cycle spends real money
across four providers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from .bot import BookClubBot

log = logging.getLogger(__name__)


def is_running(bot: BookClubBot) -> bool:
    sched = getattr(bot, "scheduler", None)
    return sched is not None and sched.running


def start_scheduler(bot: BookClubBot) -> AsyncIOScheduler | None:
    """Start the periodic jobs. Returns None if the club is already running."""
    if is_running(bot):
        log.info("Scheduler already running; not starting a second one")
        return None

    scheduler = AsyncIOScheduler()
    main_hours = bot.config.scrape_interval_hours
    gossip_hours = max(1, main_hours // 2)

    scheduler.add_job(
        _run_book_club,
        trigger=IntervalTrigger(hours=main_hours),
        kwargs={"bot": bot},
        id="book_club_main",
        name="Scrape LessWrong & discuss new posts",
        misfire_grace_time=300,
    )

    # Genuinely offset from the main job. The previous version set a *shorter
    # interval* and called it an offset — with main=2h and gossip=1h both jobs
    # realign at every even hour, and the main run calls the gossip round itself
    # at the end, so the channel got two overlapping rounds built from identical
    # context. Staggering the start by half a gossip interval separates them;
    # the club-wide lock in bot.py catches anything the stagger misses.
    scheduler.add_job(
        _run_gossip,
        trigger=IntervalTrigger(
            hours=gossip_hours,
            start_date=datetime.now() + timedelta(hours=gossip_hours / 2),
        ),
        kwargs={"bot": bot},
        id="gossip",
        name="Generate gossip",
        misfire_grace_time=300,
    )

    scheduler.start()
    bot.scheduler = scheduler
    log.info(
        "Scheduler started: main every %dh, gossip every %dh (offset %.1fh)",
        main_hours, gossip_hours, gossip_hours / 2,
    )
    return scheduler


def stop_scheduler(bot: BookClubBot) -> bool:
    """Stop the periodic jobs. Returns False if it wasn't running."""
    if not is_running(bot):
        log.info("Scheduler is not running; nothing to stop")
        return False
    bot.scheduler.shutdown(wait=False)  # type: ignore[union-attr]
    bot.scheduler = None
    log.info("Scheduler stopped")
    return True


def describe(bot: BookClubBot) -> str:
    """One-line human-readable state, for !club status."""
    if not is_running(bot):
        return "Club is **stopped**. `!club start` to begin."
    jobs = bot.scheduler.get_jobs()  # type: ignore[union-attr]
    lines = ["Club is **running**."]
    for j in jobs:
        nxt = getattr(j, "next_run_time", None)
        lines.append(f"• {j.name} — next {nxt:%H:%M} " if nxt else f"• {j.name}")
    return "\n".join(lines)


async def _run_book_club(bot: BookClubBot) -> None:
    if not bot.is_ready():
        log.warning("Bot not ready, skipping scheduled run")
        return
    try:
        await bot.process_new_posts()
    except Exception:
        log.exception("Error in scheduled book club run")


async def _run_gossip(bot: BookClubBot) -> None:
    if not bot.is_ready():
        return
    try:
        await bot._generate_gossip()
    except Exception:
        log.exception("Error in scheduled gossip run")
