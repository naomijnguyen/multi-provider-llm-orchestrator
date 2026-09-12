"""Handles posting to Discord channels via webhooks so each model gets its own identity."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .config import ModelConfig

log = logging.getLogger(__name__)

# Discord's hard per-message limit is 2000; leave a little room.
DISCORD_LIMIT = 1990


def chunk(content: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split content into Discord-sized pieces, preferring clean breaks.

    Paragraph breaks first, then line breaks, then sentence ends, and only
    mid-word as a last resort. The bot used to hard-truncate at 1900 instead,
    which silently dropped the end of anything longer — including the approval
    footer on a long draft.
    """
    if len(content) <= limit:
        return [content]

    out: list[str] = []
    rest = content
    while len(rest) > limit:
        window = rest[:limit]
        cut = -1
        for sep in ("\n\n", "\n", ". ", "! ", "? ", " "):
            found = window.rfind(sep)
            # Only accept a break in the last third, else we make tiny messages.
            if found > limit // 3:
                cut = found + len(sep)
                break
        if cut <= 0:
            cut = limit
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


async def ensure_channels(
    guild: discord.Guild, channel_names: list[str], category_name: str = "Models Only (+Jen)"
) -> dict[str, discord.TextChannel]:
    """Ensure all required channels exist in the guild. Creates missing ones."""
    # Find or create the club category
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
        log.info("Created category: %s", category_name)

    channels: dict[str, discord.TextChannel] = {}
    for name in channel_names:
        channel = discord.utils.get(guild.text_channels, name=name, category=category)
        if channel is None:
            channel = await guild.create_text_channel(name, category=category)
            log.info("Created channel: #%s", name)
        channels[name] = channel

    return channels


async def get_or_create_webhook(
    channel: discord.TextChannel, model: ModelConfig
) -> discord.Webhook:
    """Get or create a webhook for a specific model in a channel."""
    webhooks = await channel.webhooks()
    webhook_name = f"bookclub-{model.name}"

    for wh in webhooks:
        if wh.name == webhook_name:
            return wh

    webhook = await channel.create_webhook(name=webhook_name)
    log.info("Created webhook '%s' in #%s", webhook_name, channel.name)
    return webhook


async def post_as_model(
    channel: discord.TextChannel,
    model: ModelConfig,
    content: str,
) -> discord.WebhookMessage:
    """Post a message to a channel as a specific AI model (using webhooks for custom name/avatar)."""
    if not content or not content.strip():
        content = f"*[{model.display_name} is speechless.]*"
    webhook = await get_or_create_webhook(channel, model)

    pieces = chunk(content)
    message = None
    for piece in pieces:
        try:
            message = await webhook.send(
                content=piece,
                username=model.display_name,
                avatar_url=model.avatar_url,
                wait=True,  # returns the Message object
            )
        except discord.HTTPException as e:
            log.error("Failed to post as %s in #%s: %s", model.name, channel.name, e)
            # Fall back to a regular channel message, chunked again because the
            # name prefix makes it longer than the piece we just failed to send.
            for sub in chunk(f"**{model.display_name}**: {piece}"):
                message = await channel.send(sub)  # type: ignore[assignment]
    # The last message is the one carrying any footer, so reactions land there.
    return message  # type: ignore[return-value]


async def post_new_post_announcement(
    channel: discord.TextChannel,
    title: str,
    url: str,
    author: str | None,
) -> None:
    """Announce a new LessWrong post in #new-posts."""
    author_str = f" by **{author}**" if author else ""
    await channel.send(
        f"📚 **New post{author_str}:**\n"
        f"**{title}**\n"
        f"{url}"
    )


async def post_draft(
    channel: discord.TextChannel,
    model: ModelConfig,
    draft_text: str,
    post_title: str,
    post_url: str,
) -> discord.WebhookMessage:
    """Post a draft comment to #drafts. Users react with ✅ to approve."""
    content = (
        f"**Draft comment for:** [{post_title}]({post_url})\n"
        f"─────────────────────────────\n"
        f"{draft_text}\n"
        f"─────────────────────────────\n"
        f"*React with ✅ to approve posting to LessWrong*"
    )
    # No length budgeting needed: post_as_model chunks, so the approval footer
    # survives even when the draft is long. The reaction goes on the last
    # message, which is the one holding the footer.
    message = await post_as_model(channel, model, content)
    await message.add_reaction("✅")
    return message
