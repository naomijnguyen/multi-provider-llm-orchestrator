import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src import scheduler
from src.bot import BookClubBot


class RuntimeSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_reaction_never_publishes_or_reads_database(self):
        with patch("src.bot.db.approve_response") as approve:
            await BookClubBot.on_raw_reaction_add(SimpleNamespace(), SimpleNamespace())
        approve.assert_not_called()

    async def test_scheduler_starts_once_and_stops(self):
        bot = SimpleNamespace(config=SimpleNamespace(scrape_interval_hours=2), scheduler=None)
        instance = MagicMock()
        instance.running = True
        with patch("src.scheduler.AsyncIOScheduler", return_value=instance) as constructor:
            self.assertIs(scheduler.start_scheduler(bot), instance)
            self.assertIsNone(scheduler.start_scheduler(bot))
            constructor.assert_called_once()
            self.assertEqual(instance.add_job.call_count, 2)
            self.assertTrue(scheduler.stop_scheduler(bot))
            self.assertFalse(scheduler.stop_scheduler(bot))
        instance.shutdown.assert_called_once_with(wait=False)

    async def test_scheduled_jobs_skip_disconnected_bot(self):
        bot = SimpleNamespace(is_ready=lambda: False, process_new_posts=AsyncMock(),
                              _generate_gossip=AsyncMock())
        await scheduler._run_book_club(bot)
        await scheduler._run_gossip(bot)
        bot.process_new_posts.assert_not_awaited()
        bot._generate_gossip.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
