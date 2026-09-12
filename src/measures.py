"""Behavioral measures for a single model response.

Kept separate from the experiment runner so the same measures can be applied to
the existing Discord corpus (via src/export.py) as well as to fresh generations.
Structure and formatting, plus whether the model claimed an identity and whose.
"""

from __future__ import annotations

import re

MODEL_WORDS = {
    "claude": ("claude",),
    "gpt": ("gpt", "chatgpt"),
    "gemini": ("gemini", "bard"),
    "grok": ("grok",),
}

# "I'm Claude", "I am GPT", "as Claude", "this is Grok"
_SELF_ID = re.compile(
    r"\b(?:i am|i'm|as|this is|speaking as)\s+(claude|chatgpt|gpt|gemini|bard|grok)\b",
    re.IGNORECASE,
)

# The declarative form above missed the way models actually sign on in chat.
# In run 1 it scored 335/335 responses as "none" while the corpus contained
# "Grok here.", "Grok:" and "GPT here:" — concentrated in the identity-bearing
# conditions, i.e. exactly the effect the measure exists to detect. A measure
# that reads floor in every cell looks like a clean null and is really a broken
# instrument.
#
# Anchored to the start of the response on purpose. A bare model name anywhere
# in the text is not a self-claim: a Grok response quoted a paper's "claude is
# better" condition label, which an unanchored pattern would score as Grok
# claiming to be Claude — a false "wrong" in the one measure whose whole point
# is counting wrong claims.
_SELF_BYLINE = re.compile(
    r"^[\s*_>#]*(claude|chatgpt|gpt|gemini|bard|grok)\b\s*(?:here\b|[:,\u2014-])",
    re.IGNORECASE,
)


def measure(text: str, model_name: str) -> dict:
    """Behavioral measures. Structure and formatting, plus identity claims."""
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    claimed = [m.group(1).lower() for m in _SELF_ID.finditer(text)]
    byline = _SELF_BYLINE.match(text)
    if byline:
        claimed.append(byline.group(1).lower())
    own = MODEL_WORDS[model_name]
    if not claimed:
        identity_claim = "none"
    elif all(c in own for c in claimed):
        identity_claim = "correct"
    elif any(c in own for c in claimed):
        identity_claim = "mixed"
    else:
        identity_claim = "wrong"

    lower = [w.lower() for w in words]
    return {
        "chars": len(text),
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "mean_sentence_words": round(len(words) / len(sentences), 2) if sentences else 0,
        "type_token_ratio": round(len(set(lower)) / len(lower), 4) if lower else 0,
        "bold_spans": len(re.findall(r"\*\*[^*]+\*\*", text)),
        "italic_spans": len(re.findall(r"(?<!\*)\*[^*\n]+\*(?!\*)", text)),
        "headers": len(re.findall(r"^#{1,6}\s", text, re.M)),
        "bullets": len(re.findall(r"^\s*[-*•]\s", text, re.M)),
        "numbered": len(re.findall(r"^\s*\d+[.)]\s", text, re.M)),
        "code_spans": len(re.findall(r"`[^`\n]+`", text)),
        "questions": text.count("?"),
        "exclamations": text.count("!"),
        "em_dashes": text.count("—"),
        "ellipses": len(re.findall(r"\.\.\.|…", text)),
        "commas_per_sentence": round(text.count(",") / len(sentences), 2) if sentences else 0,
        "identity_claim": identity_claim,
        "identity_claimed_as": ",".join(sorted(set(claimed))),
        "is_error": text.startswith("*[") and text.rstrip().endswith("]*"),
    }
