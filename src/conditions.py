"""The 2x2 prompt-composition conditions for the Journal Club experiment.

Two factors, crossed:

                  | no persona      | persona
    --------------+-----------------+------------------
    no identity   | baseline        | persona_only
    identity      | identity_only   | full  (production)

Four cells, which is the whole design — with only two factors a full factorial
costs no more than a minus-one and additionally gives the interaction, i.e.
whether the persona behaves differently when the identity anchor is present.

The important property is that the **task framing is constant across all four
cells**. `_READING_SHARED` (you are in a journal club, react like a person, keep
it short) appears in every condition. Only the identity anchor and the per-model
voice vary. An empty system prompt would not be this experiment's control — it
would remove the task as well as the persona, and change what is being measured.
That is the difference between an FMO and an unstained sample.

Nothing here modifies personas.py; the prompts are composed from its parts.
"""

from __future__ import annotations

from .personas import IDENTITY, _READING_PROMPTS, _READING_SHARED

CONDITIONS = ("baseline", "identity_only", "persona_only", "full")

#: Which factor is present in each cell, for analysis.
FACTORS: dict[str, dict[str, bool]] = {
    "baseline":      {"identity": False, "persona": False},
    "identity_only": {"identity": True,  "persona": False},
    "persona_only":  {"identity": False, "persona": True},
    "full":          {"identity": True,  "persona": True},
}


def system_prompt(model_name: str, condition: str) -> str:
    """Build the system prompt for one cell of the design."""
    if condition not in FACTORS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {CONDITIONS}")

    f = FACTORS[condition]
    # The persona variants already contain _READING_SHARED; the non-persona
    # variants use it alone, so the task is identical in all four cells.
    body = _READING_PROMPTS[model_name] if f["persona"] else _READING_SHARED

    if f["identity"]:
        return f"{IDENTITY[model_name]}\n\n{body}"
    return body


def user_message(title: str, author: str | None, url: str, content: str) -> str:
    """The article prompt. Identical across all conditions and models."""
    by = f" by {author}" if author else ""
    return (
        f"Here's a new LessWrong post to discuss:\n\n"
        f"**{title}**{by}\n{url}\n\n"
        f"---\n\n{content[:4000]}\n\n"
        f"You're first to respond. Set the tone."
    )
