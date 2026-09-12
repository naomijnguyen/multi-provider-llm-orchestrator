from __future__ import annotations

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

from . import db

log = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://www.lesswrong.com/feed.xml",
    "https://www.alignmentforum.org/feed.xml",
]


def scrape_feed(db_path: str, feed_urls: list[str] | None = None) -> list[dict]:
    """Fetch each feed and store any new posts. Returns list of newly added posts."""
    new_posts: list[dict] = []
    for feed_url in (feed_urls or DEFAULT_FEEDS):
        new_posts.extend(_scrape_one(db_path, feed_url))
    return new_posts


def _scrape_one(db_path: str, feed_url: str) -> list[dict]:
    """Fetch a single RSS feed and store any new posts."""
    log.info("Fetching RSS feed from %s", feed_url)
    feed = feedparser.parse(feed_url)

    if feed.bozo:
        log.warning("Feed parse warning: %s", feed.bozo_exception)

    new_posts = []
    for entry in feed.entries:
        lw_id = entry.get("id", entry.get("link", ""))
        title = entry.get("title", "Untitled")
        url = entry.get("link", "")
        author = entry.get("dc_creator") or entry.get("author")
        content = _extract_text(entry.get("description", "") or entry.get("summary", ""))

        published_at = None
        if pub := entry.get("published"):
            try:
                published_at = parsedate_to_datetime(pub)
            except Exception:
                pass

        post_id = db.insert_post(
            db_path,
            lw_id=lw_id,
            title=title,
            url=url,
            author=author,
            published_at=published_at,
            content=content,
        )

        if post_id is not None:
            post = db.get_post(db_path, post_id)
            if post:
                new_posts.append(post)
                log.info("New post: %s", title)

    log.info(
        "Scrape complete for %s: %d new posts out of %d entries",
        feed_url, len(new_posts), len(feed.entries),
    )
    return new_posts


def _extract_text(html: str) -> str:
    """Strip HTML tags and return clean text, preserving paragraph breaks."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style elements
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Get text with newlines between block elements
    text = soup.get_text(separator="\n", strip=True)

    # Collapse excessive whitespace but keep paragraph breaks
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)
