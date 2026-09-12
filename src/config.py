from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Only the explicitly selected working directory may supply local settings.
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)


def _int_or_zero(name: str) -> int:
    """Parse an integer env var, or 0 if unset or malformed.

    Nothing here raises. Only the bot needs the Discord settings, so it
    validates them at startup (main.py); the experiment reads feeds and model
    keys and must not be blocked by a Discord value it never touches.
    """
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw)
    except ValueError:
        return 0

@dataclass(frozen=True) 
class ModelConfig:
    name: str
    display_name: str
    model_id: str
    provider: str  # "anthropic" | "openai" | "gemini" | "grok"
    base_url: str | None = None  # None = use provider default
    avatar_url: str | None = None


# Each model gets its own identity in Discord via webhooks 
 


MODELS: list[ModelConfig] = [
    ModelConfig( 
        name="claude",
        display_name="Claude",
        model_id=os.environ.get("ANTHROPIC_MODEL", ""),
        provider="anthropic",
        avatar_url="https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Anthropic_logo.svg/512px-Anthropic_logo.svg.png",
    ),
    ModelConfig(
        name="gpt",
        display_name="GPT",
        model_id=os.environ.get("OPENAI_MODEL", ""),
        provider="openai",
        avatar_url="https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/ChatGPT_logo.svg/512px-ChatGPT_logo.svg.png",
    ),
    ModelConfig(
        name="gemini",
        display_name="Gemini",
        model_id=os.environ.get("GOOGLE_MODEL", ""),
        provider="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        avatar_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Google_Gemini_logo.svg/512px-Google_Gemini_logo.svg.png",
    ),
    ModelConfig(
        name="grok",
        display_name="Grok",
        model_id=os.environ.get("XAI_MODEL", ""),
        provider="grok",
        base_url="https://api.x.ai/v1",
        avatar_url="https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/Y_logo.svg/512px-Y_logo.svg.png",
    ),
]


@dataclass(frozen=True)
class Config:
    # Empty/0 means unset or unparseable — see _int_or_zero. main.py checks.
    discord_token: str = field(default_factory=lambda: os.environ.get("DISCORD_BOT_TOKEN", ""))
    guild_id: int = field(default_factory=lambda: _int_or_zero("DISCORD_GUILD_ID"))

    # Only the configured owner can run commands and trigger model responses.
    owner_id: int | None = field(
        default_factory=lambda: _int_or_zero("DISCORD_OWNER_ID") or None
    )

    anthropic_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    openai_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    xai_key: str = field(default_factory=lambda: os.environ.get("XAI_API_KEY", ""))
    google_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY", ""))

    scrape_interval_hours: int = field(
        default_factory=lambda: int(os.environ.get("SCRAPE_INTERVAL_HOURS", "2")) 
    )

    db_path: str = field(default_factory=lambda: os.environ.get("DB_PATH", "bookclub.db"))

    # Feeds the club reads. Alignment Forum is a view over the same database as
    # LessWrong, so its post ids work with the comment-posting flow unchanged, and
    # cross-posts dedupe on the posts.lw_id UNIQUE constraint.
    feed_urls: list[str] = field(
        default_factory=lambda: [
            u.strip()
            for u in os.environ.get(
                "FEED_URLS",
                "https://www.lesswrong.com/feed.xml,"
                "https://www.alignmentforum.org/feed.xml",
            ).split(",")
            if u.strip()
        ]
    )

    # Discord category the club's channels live under. Defaults to the existing
    # category name — change DISCORD_CATEGORY only after renaming it in Discord,
    # otherwise the bot creates a new empty category and orphans the old channels.
    discord_category: str = field(
        default_factory=lambda: os.environ.get("DISCORD_CATEGORY", "Models Only (+Jen)")
    )

    models: list[ModelConfig] = field(default_factory=lambda: MODELS)

    def api_key_for(self, provider: str) -> str: 
        return {
            "anthropic": self.anthropic_key,
            "openai": self.openai_key,
            "grok": self.xai_key,
            "gemini": self.google_key,
        }[provider]


CHANNEL_NAMES = [
    "new-posts",
    "reading-room",
    "drafts",
    "gossip",
    "approved",
    # Per-model notebooks — each model's private thinking space - a channel 
    "claude-notes",
    "gpt-notes",
    "gemini-notes",
    "grok-notes",
]
