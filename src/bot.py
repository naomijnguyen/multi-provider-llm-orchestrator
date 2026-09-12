"""Journal Club — Discord bot where the AI models live."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from . import db
from .channels import (
    ensure_channels,
    post_as_model,
    post_draft,
    post_new_post_announcement,
)
from .config import CHANNEL_NAMES
from .models import generate
from .personas import DRAFT_PROMPT, GOSSIP_PROMPTS, NOTES_PROMPTS, READING_PROMPTS

if TYPE_CHECKING:
    from .config import Config

log = logging.getLogger(__name__)

# Most posts a single run will process. Both feeds return ~10 items each, and
# every post costs 4 notes calls + 4 discussion calls + 1 draft — a clean
# database is ~180 model calls in one uninterruptible loop without this.
MAX_POSTS_PER_RUN = 3


class BookClubBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.club_channels: dict[str, discord.TextChannel] = {}
        self.scheduler = None  # set by scheduler.start_scheduler
        # The club does one thing at a time. Two scheduled jobs, the !gossip
        # command and on_message can all fire concurrently into the same
        # channels, on the same budget, building context from the same reads.
        self._club_lock = asyncio.Lock()

    async def setup_hook(self) -> None:
        db.init_db(self.config.db_path)
        log.info("Database initialized at %s", self.config.db_path)

    async def on_ready(self) -> None:
        log.info("Bot is ready as %s", self.user)
        guild = self.get_guild(self.config.guild_id)
        if guild is None:
            log.error("Could not find guild %s", self.config.guild_id)
            return
        self.club_channels = await ensure_channels(
            guild, CHANNEL_NAMES, self.config.discord_category
        )
        log.info("Channels ready: %s", list(self.club_channels.keys()))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle ✅ reactions on draft messages to approve posting to LessWrong."""
        if not self.config.enable_public_posting or payload.guild_id != self.config.guild_id:
            return
        if str(payload.emoji) != "✅":
            return
        # Ignore the bot's own reactions (it adds ✅ as a prompt)
        if payload.user_id == self.user.id:  # type: ignore[union-attr]
            return

        drafts_channel = self.club_channels.get("drafts")
        if drafts_channel is None or payload.channel_id != drafts_channel.id:
            return

        # Approving publishes a model-written comment to LessWrong under a real
        # account, using a ~5-year credential. Only the owner may do that, and
        # with no owner configured this fails closed.
        if self.config.owner_id is None:
            log.warning(
                "Ignoring the approval from %s: DISCORD_OWNER_ID is unset, so "
                "nothing may be published to LessWrong.",
                payload.user_id,
            )
            return
        if payload.user_id != self.config.owner_id:
            log.warning("Ignoring the approval from non-owner %s", payload.user_id)
            return

        message_id = str(payload.message_id)
        response = db.approve_response(self.config.db_path, message_id)
        if response is None:
            return
        # approve_response sets `approved` but leaves `posted_to_lw` alone, so a
        # re-added reaction on an already-published draft arrives here. Without
        # this the comment posts to LessWrong a second time.
        if response["posted_to_lw"]:
            log.info(
                "Response %s is already posted to LessWrong; ignoring", response["id"]
            )
            return

        log.info("Response %s approved for LessWrong posting", response["id"])

        # Post to LessWrong if we have a token
        if self.config.lw_auth_token:
            from .lesswrong import post_comment

            post = db.get_post(self.config.db_path, response["post_id"])
            if post:
                success = await post_comment(
                    self.config.lw_auth_token,
                    post_id=post["lw_id"],
                    body=response["response_text"],
                )
                if success:
                    db.mark_posted_to_lw(self.config.db_path, response["id"])
                    approved_ch = self.club_channels.get("approved")
                    if approved_ch:
                        await approved_ch.send(
                            f"✅ Posted comment to LessWrong: **{post['title']}**\n{post['url']}"
                        )
        else:
            approved_ch = self.club_channels.get("approved")
            if approved_ch:
                await approved_ch.send(
                    "⚠️ Comment approved but no `LESSWRONG_AUTH_TOKEN` configured. "
                    "Set it in `.env` to enable auto-posting."
                )

    # ── Interactive: respond when Jen posts in channels ─────────

    async def on_message(self, message: discord.Message) -> None:
        """When Jen posts in #reading-room or #gossip, models respond."""
        # Let commands still work
        await self.process_commands(message)

        # Ignore bots (including our own webhooks)
        if message.author.bot:
            return

        # Only the owner drives the models. Otherwise any server member can spend
        # four providers' tokens at will, and whatever they write becomes context
        # the drafter reads on its way to a public comment.
        if self.config.owner_id is None or message.author.id != self.config.owner_id:
            return
        if message.guild is None or message.guild.id != self.config.guild_id:
            return

        # Only respond in our club channels
        channel_name = getattr(message.channel, "name", "")
        if channel_name not in ("reading-room", "gossip"):
            return
        configured_channel = self.club_channels.get(channel_name)
        if configured_channel is None or configured_channel.id != message.channel.id:
            return

        # Don't respond to commands
        if message.content.startswith("!"):
            return

        log.info("Jen posted in #%s: %s", channel_name, message.content[:80])

        # Gather recent message history for context
        recent_history = []
        async for msg in message.channel.history(limit=15, before=message):
            author_name = msg.author.display_name or msg.author.name
            recent_history.append(f"**{author_name}**: {msg.content}")
        recent_history.reverse()
        recent_history.append(f"**Jen**: {message.content}")

        history_text = "\n\n".join(recent_history[-10:])  # last 10 messages

        if channel_name == "reading-room":
            await self._respond_to_jen_reading(message.channel, history_text, message.content)
        elif channel_name == "gossip":
            await self._respond_to_jen_gossip(message.channel, history_text, message.content)

    async def _respond_to_jen_reading(
        self, channel: discord.TextChannel, history: str, jen_msg: str
    ) -> None:
        """Models respond to Jen's message in #reading-room."""
        for model_cfg in self.config.models:
            prompt = READING_PROMPTS.get(model_cfg.name)
            if not prompt:
                continue

            user_msg = (
                f"Conversation in #reading-room:\n\n{history}\n\n"
                f"---\n\nJen just said something. Respond to her — and to the "
                f"conversation. Keep it natural, group chat energy."
            )

            response_text = await generate(
                self.config, model_cfg, prompt, user_msg
            )

            await post_as_model(channel, model_cfg, response_text)
            await asyncio.sleep(2)

    async def _respond_to_jen_gossip(
        self, channel: discord.TextChannel, history: str, jen_msg: str
    ) -> None:
        """Models respond to Jen's message in #gossip."""
        for model_cfg in self.config.models:
            prompt = GOSSIP_PROMPTS.get(model_cfg.name)
            if not prompt:
                continue

            user_msg = (
                f"Conversation in #gossip:\n\n{history}\n\n"
                f"---\n\nJen just dropped into the chat. Respond to her — "
                f"react, banter, roast, whatever feels right."
            )

            response_text = await generate(
                self.config, model_cfg, prompt, user_msg, max_tokens=2048
            )

            await post_as_model(channel, model_cfg, response_text)
            await asyncio.sleep(3)

    # ── Core book club flow ──────────────────────────────────────

    async def process_new_posts(self) -> None:
        """Main flow: scrape, announce, discuss, draft, gossip."""
        async with self._club_lock:
            await self._process_new_posts()

    async def _process_new_posts(self) -> None:
        from .scraper import scrape_feed

        # Scrape for brand-new posts from RSS.
        # feedparser.parse does its own blocking HTTP fetch. Called inline it
        # stalled the Discord heartbeat for the length of both feed requests,
        # and those reconnects are what used to stack up duplicate schedulers.
        freshly_scraped = await asyncio.to_thread(
            scrape_feed, self.config.db_path, self.config.feed_urls
        )

        # Also pick up any unprocessed posts from previous runs
        all_new = db.get_new_posts(self.config.db_path)

        if not all_new:
            log.info("No new posts to process")
            return

        log.info("Processing %d posts (%d freshly scraped)", len(all_new), len(freshly_scraped))

        # Only announce freshly scraped ones (don't re-announce old unprocessed posts)
        freshly_scraped_ids = {p["id"] for p in freshly_scraped}

        announce_ch = self.club_channels.get("new-posts")
        reading_ch = self.club_channels.get("reading-room")
        drafts_ch = self.club_channels.get("drafts")

        if len(all_new) > MAX_POSTS_PER_RUN:
            log.info(
                "Capping this run at %d of %d pending posts",
                MAX_POSTS_PER_RUN, len(all_new),
            )

        for post in all_new[:MAX_POSTS_PER_RUN]:
            # One post's failure must not take down the batch. Previously an
            # exception here skipped every remaining post AND left this one at
            # status='new', so the next run started on the same post and failed
            # the same way — the bot appeared to find exactly one post, forever.
            try:
                # Announce (only freshly scraped posts, not old unprocessed ones)
                if announce_ch and post["id"] in freshly_scraped_ids:
                    await post_new_post_announcement(
                        announce_ch, post["title"], post["url"], post["author"]
                    )

                # Each model reads and reacts
                if reading_ch:
                    await self._discuss_post(reading_ch, post)

                # Pick a model to draft a comment
                if drafts_ch:
                    await self._draft_comment(drafts_ch, post)
            except Exception:
                # 'failed' rather than 'discussed': it stays out of the retry
                # loop but is still visible, and re-runnable by hand once the
                # cause is fixed.
                log.exception(
                    "Failed processing post %s (%s)", post["id"], post["title"]
                )
                db.mark_post_status(self.config.db_path, post["id"], "failed")
            else:
                db.mark_post_status(self.config.db_path, post["id"], "discussed")

        # Gossip after processing. Calls the unlocked round directly — we
        # already hold the club lock, and asyncio.Lock is not reentrant.
        await self._gossip_round()

    async def _discuss_post(self, channel: discord.TextChannel, post: dict) -> None:
        """Have each model jot notes, then share their take on a post."""
        article_text = post.get("content") or post["title"]
        # Truncate to avoid token limits — first ~4000 chars is usually enough
        article_text = article_text[:4000]

        user_msg = (
            f"Here's a new LessWrong post to discuss:\n\n"
            f"**{post['title']}**"
            f"{' by ' + post['author'] if post.get('author') else ''}\n"
            f"{post['url']}\n\n"
            f"---\n\n{article_text}"
        )

        # Phase 1: Each model jots notes in their private channel
        for model_cfg in self.config.models:
            notes_ch = self.club_channels.get(f"{model_cfg.name}-notes")
            notes_prompt = NOTES_PROMPTS.get(model_cfg.name)
            if notes_ch and notes_prompt:
                notes_text = await generate(
                    self.config, model_cfg, notes_prompt, user_msg, max_tokens=2048
                )
                await post_as_model(notes_ch, model_cfg, f"**Notes on: {post['title']}**\n{notes_text}")
                # Persist, like discussion/draft/gossip. These were the only
                # generations the club threw away — posted to Discord and never
                # written down — so the private-notes channel existed solely as
                # Discord state, and became unreachable the moment the bot token
                # lapsed. It is also the most interesting channel to analyse: a
                # model's private take before the group discussion, which is
                # what you compare a chain of thought against.
                db.insert_response(
                    self.config.db_path,
                    post_id=post["id"],
                    model_name=model_cfg.name,
                    response_text=notes_text,
                    response_type="notes",
                )

        # Phase 2: Group discussion in #reading-room
        # Build up conversation as each model responds so later models can react
        discussion_so_far: list[str] = []

        for model_cfg in self.config.models:
            prompt = READING_PROMPTS.get(model_cfg.name)
            if not prompt:
                continue

            # Include what other models have said so far
            if discussion_so_far:
                thread = "\n\n".join(discussion_so_far)
                full_msg = (
                    f"{user_msg}\n\n"
                    f"---\n\n**Discussion so far:**\n\n{thread}\n\n"
                    f"---\n\nNow share your take. You can respond to the article "
                    f"AND react to what others have said — agree, disagree, riff, whatever."
                )
            else:
                full_msg = f"{user_msg}\n\nYou're first to respond. Set the tone."

            response_text = await generate(
                self.config, model_cfg, prompt, full_msg
            )

            discussion_so_far.append(
                f"**{model_cfg.display_name}**: {response_text}"
            )

            message = await post_as_model(channel, model_cfg, response_text)

            db.insert_response(
                self.config.db_path,
                post_id=post["id"],
                model_name=model_cfg.name,
                response_text=response_text,
                response_type="discussion",
                discord_message_id=str(message.id),
            )

            # Small delay between models so it feels like a conversation
            await asyncio.sleep(2)

    async def _draft_comment(self, channel: discord.TextChannel, post: dict) -> None:
        """Pick a model to draft a polished LessWrong comment."""
        # Grab the discussion so far
        responses = db.get_responses_for_post(
            self.config.db_path, post["id"], response_type="discussion"
        )
        discussion_text = "\n\n".join(
            f"**{r['model_name']}**: {r['response_text']}" for r in responses
        )

        # Claude always drafts — it's going under Jen's name
        drafter = next(m for m in self.config.models if m.name == "claude")
        article_text = (post.get("content") or post["title"])[:4000]

        user_msg = (
            f"Article: **{post['title']}**\n\n{article_text}\n\n"
            f"---\n\nDiscussion so far:\n{discussion_text}\n\n"
            f"---\n\nNow draft a polished comment for LessWrong."
        )

        draft_text = await generate(
            self.config, drafter, DRAFT_PROMPT, user_msg
        )

        message = await post_draft(
            channel, drafter, draft_text, post["title"], post["url"]
        )

        db.insert_response(
            self.config.db_path,
            post_id=post["id"],
            model_name=drafter.name,
            response_text=draft_text,
            response_type="draft",
            discord_message_id=str(message.id),
        )

    async def _generate_gossip(self) -> None:
        """Models gossip in #gossip. Takes the club lock; use _gossip_round if
        you already hold it."""
        async with self._club_lock:
            await self._gossip_round()

    async def _gossip_round(self) -> None:
        gossip_ch = self.club_channels.get("gossip")
        if gossip_ch is None:
            return

        # Grab recent gossip for context
        recent = db.get_recent_gossip(self.config.db_path, limit=10)
        context = "\n".join(
            f"{g['model_name']}: {g['response_text']}" for g in reversed(recent)
        )

        # Also grab what they've been reading recently
        recent_posts = db.get_recent_posts(self.config.db_path, limit=5)
        reading_context = ", ".join(p["title"] for p in recent_posts)

        for model_cfg in self.config.models:
            prompt = GOSSIP_PROMPTS.get(model_cfg.name)
            if not prompt:
                continue

            user_msg = (
                f"Recent conversation in the gossip channel:\n{context}\n\n"
                f"Posts you've been reading recently: {reading_context}\n\n"
                f"Say something — gossip, react to the others, joke around, do something fun, write some prose "
                f"or just riff."
            ) if context else (
                f"You're kicking off the gossip channel for the day. "
                f"Posts you've been reading recently: {reading_context}\n\n"
                f"Start some banter."
            )

            response_text = await generate(
                self.config, model_cfg, prompt, user_msg, max_tokens=2048
            )

            message = await post_as_model(gossip_ch, model_cfg, response_text)

            db.insert_response(
                self.config.db_path,
                post_id=None,  # gossip isn't tied to a specific post
                model_name=model_cfg.name,
                response_text=response_text,
                response_type="gossip",
                discord_message_id=str(message.id),
            )

            await asyncio.sleep(3)  # stagger for natural feel
