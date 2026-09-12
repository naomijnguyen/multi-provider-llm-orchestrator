from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator


def init_db(path: str) -> None:
    with _connect(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                lw_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                published_at TIMESTAMP,
                content TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY,
                post_id INTEGER REFERENCES posts(id),
                model_name TEXT NOT NULL,
                response_text TEXT NOT NULL,
                response_type TEXT DEFAULT 'discussion',
                approved BOOLEAN DEFAULT FALSE,
                posted_to_lw BOOLEAN DEFAULT FALSE,
                discord_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


@contextmanager
def _connect(path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Durability. The scheduler scrapes on a timer while the bot handles
    # commands, so writes interleave. WAL survives that; the default rollback
    # journal is what left the old bookclub.db with a corrupt b-tree page.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Posts ──────────────────────────────────────────────────────────

def insert_post(
    path: str,
    *,
    lw_id: str,
    title: str,
    url: str,
    author: str | None,
    published_at: datetime | None,
    content: str | None,
) -> int | None:
    """Insert a post if it doesn't already exist. Returns the row id, or None if duplicate."""
    with _connect(path) as conn:
        try:
            cur = conn.execute(
                """INSERT INTO posts (lw_id, title, url, author, published_at, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (lw_id, title, url, author, published_at, content),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_new_posts(path: str) -> list[dict[str, Any]]:
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'new' ORDER BY published_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_post_status(path: str, post_id: int, status: str) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))


def get_post(path: str, post_id: int) -> dict[str, Any] | None:
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None


def get_recent_posts(path: str, limit: int = 10) -> list[dict[str, Any]]:
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY published_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Responses ─────────────────────────────────────────────────────

def insert_response(
    path: str,
    *,
    post_id: int | None,
    model_name: str,
    response_text: str,
    response_type: str = "discussion",
    discord_message_id: str | None = None,
) -> int:
    with _connect(path) as conn:
        cur = conn.execute(
            """INSERT INTO responses (post_id, model_name, response_text, response_type, discord_message_id)
               VALUES (?, ?, ?, ?, ?)""",
            (post_id, model_name, response_text, response_type, discord_message_id),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_responses_for_post(
    path: str, post_id: int, response_type: str | None = None
) -> list[dict[str, Any]]:
    with _connect(path) as conn:
        if response_type:
            rows = conn.execute(
                "SELECT * FROM responses WHERE post_id = ? AND response_type = ? ORDER BY created_at",
                (post_id, response_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM responses WHERE post_id = ? ORDER BY created_at",
                (post_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def approve_response(path: str, discord_message_id: str) -> dict[str, Any] | None:
    """Mark a response as approved by its Discord message ID. Returns the response if found."""
    with _connect(path) as conn:
        conn.execute(
            "UPDATE responses SET approved = TRUE WHERE discord_message_id = ?",
            (discord_message_id,),
        )
        row = conn.execute(
            "SELECT * FROM responses WHERE discord_message_id = ?",
            (discord_message_id,),
        ).fetchone()
        return dict(row) if row else None


def mark_posted_to_lw(path: str, response_id: int) -> None:
    with _connect(path) as conn:
        conn.execute(
            "UPDATE responses SET posted_to_lw = TRUE WHERE id = ?", (response_id,)
        )


def get_recent_gossip(path: str, limit: int = 20) -> list[dict[str, Any]]:
    with _connect(path) as conn:
        rows = conn.execute(
            """SELECT * FROM responses WHERE response_type = 'gossip'
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
