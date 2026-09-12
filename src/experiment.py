"""Run the 2x2 prompt-composition experiment and write a CSV for analysis.

    python -m src.experiment --papers 5 --reps 3

Design: 4 conditions x 4 models x N papers x R replicates. Replicates matter —
generation is stochastic, so without them a condition effect cannot be told
apart from sampling spread. Same reason you run a control in triplicate.

This never touches Discord and never writes to the production database. Papers
are scraped into a throwaway database inside the output directory, so the club's
own state is untouched by the experiment.

Output: one row per generation, with the raw response and the computed measures,
in `experiment_runs.csv`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime

from .conditions import CONDITIONS, FACTORS, system_prompt, user_message
from .measures import measure
from . import db
from .config import Config
from .models import generate_detailed
from .scraper import scrape_feed
from .run_inputs import validate_request, validate_papers

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# How many generations may be in flight at once. Modest, to stay clear of
# per-provider rate limits without making a 240-call run take an hour.
CONCURRENCY = 4

FIELDS = [
    "run_id", "timestamp", "paper_id", "paper_title", "model", "model_id",
    "condition", "has_identity", "has_persona", "rep",
    "article_chars", "article_chars_used",
    "chars", "words", "sentences", "paragraphs", "mean_sentence_words",
    "type_token_ratio", "bold_spans", "italic_spans", "headers", "bullets",
    "numbered", "code_spans", "questions", "exclamations", "em_dashes",
    "ellipses", "commas_per_sentence", "identity_claim", "identity_claimed_as",
    "is_error", "finish_reason", "hit_token_cap",
    "had_thinking", "thinking_blocks", "thinking_chars",
    "reasoning_tokens", "reasoning_chars", "reasoning_text", "response",
]


async def _one(sem, config, model_cfg, cond, paper, rep, run_id):
    async with sem:
        # max_len=None: the 1900-char cut exists for Discord. Applying it here
        # would censor response length, which is one of the measures.
        gen = await generate_detailed(
            config,
            model_cfg,
            system_prompt(model_cfg.name, cond),
            user_message(paper["title"], paper.get("author"), paper["url"],
                         paper.get("content") or paper["title"]),
            max_len=None,
        )
        text = gen.text
    row = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "paper_id": paper["id"],
        "paper_title": paper["title"],
        "model": model_cfg.name,
        "model_id": model_cfg.model_id,
        "condition": cond,
        "has_identity": FACTORS[cond]["identity"],
        "has_persona": FACTORS[cond]["persona"],
        "rep": rep,
        # Both lengths, because the runner truncates at 4000 and most articles
        # exceed it. Recording only the truncated length makes it a near-
        # constant, and a variable with no variance cannot be ruled out as a
        # confound — which is exactly what happened when the paper effect on
        # reasoning turned up: 7 of 10 articles sat at the cap, so "does a
        # longer article provoke more reasoning" was unanswerable.
        "article_chars": len(paper.get("content") or ""),
        "article_chars_used": min(len(paper.get("content") or paper["title"]), 4000),
        # finish_reason distinguishes a response that ended on its own from one
        # cut off at max_tokens. The latter is censored data — exclude it, or at
        # least never treat its length as the model's chosen length.
        "finish_reason": gen.finish_reason,
        "hit_token_cap": gen.hit_token_cap,
        # Blank means unknown, never zero: blank in had_thinking/thinking_blocks
        # is "this provider does not report reasoning"; blank in thinking_chars
        # is "a thinking block was present but its text was withheld".
        "had_thinking": "" if gen.had_thinking is None else gen.had_thinking,
        "thinking_blocks": "" if gen.thinking_blocks is None else gen.thinking_blocks,
        "thinking_chars": "" if gen.thinking_chars is None else gen.thinking_chars,
        # Reasoning effort, reported by every provider even where the text is
        # withheld — the only reasoning quantity comparable across models.
        "reasoning_tokens": "" if gen.reasoning_tokens is None else gen.reasoning_tokens,
        "reasoning_chars": "" if gen.reasoning_text is None else len(gen.reasoning_text),
        "reasoning_text": gen.reasoning_text or "",
        "response": text,
    }
    row.update(measure(text, model_cfg.name))
    log.info("%-14s %-13s p%-3s r%s  %4d chars  id=%s",
             model_cfg.name, cond, paper["id"], rep, len(text), row["identity_claim"])
    return row


async def run(config: Config, n_papers: int, reps: int, out_dir: str,
              only_models: list[str] | None = None,
              reuse_papers: str | None = None) -> str:
    validate_request(n_papers, reps, out_dir, [m.name for m in config.models], only_models)

    # Throwaway database — the experiment must not touch club state.
    # scrape_feed assumes an initialized schema (in the bot, setup_hook does
    # that); against a fresh file we have to create it ourselves.
    if reuse_papers:
        # Backfilling a model onto an existing run has to use the *same* stimuli.
        # The feeds move, so scraping again would silently substitute different
        # papers and make the arms incomparable.
        with open(reuse_papers, encoding="utf-8") as fh:
            papers = json.load(fh)
        papers = validate_papers(papers)[:n_papers]
        os.makedirs(out_dir, exist_ok=False)
        log.info("Reusing %d papers from %s", len(papers), reuse_papers)
    else:
        os.makedirs(out_dir, exist_ok=False)
        # Fresh each run. scrape_feed dedupes on posts.lw_id, so re-using a
        # scratch database from a previous run returns zero new papers and the
        # run exits having done nothing — leaving the old CSV in place, which
        # looks like a result until you check the timestamps.
        scratch_db = os.path.join(out_dir, "_papers.db")
        db.init_db(scratch_db)
        papers = await asyncio.to_thread(scrape_feed, scratch_db, config.feed_urls)
        if not papers:
            sys.exit("No papers returned from the feeds. Nothing to run.")
        papers = papers[:n_papers]

    # Record the exact stimulus set so another model can be run against it later.
    with open(os.path.join(out_dir, "papers.json"), "w", encoding="utf-8") as fh:
        json.dump([{k: p[k] for k in ("id", "lw_id", "title", "url", "author", "content")}
                   for p in papers], fh, indent=1, default=str)
    log.info("Using %d papers: %s", len(papers), "; ".join(p["title"][:40] for p in papers))

    models = [m for m in config.models
              if only_models is None or m.name in only_models]
    if not models:
        sys.exit(f"No models matched {only_models}")

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        _one(sem, config, m, cond, paper, rep, run_id)
        for paper in papers
        for m in models
        for cond in CONDITIONS
        for rep in range(1, reps + 1)
    ]
    log.info("Running %d generations (%d conditions x %d models x %d papers x %d reps)",
             len(tasks), len(CONDITIONS), len(models), len(papers), reps)

    # Written as each generation completes, not gathered and written at the end.
    # A run of this length can be interrupted — by a quota wall, a rate limit, or
    # Ctrl-C — and losing every completed generation because the last one never
    # arrived wastes tokens already paid for. Row order is non-deterministic;
    # every row carries its own paper/model/condition/rep, so order is not
    # information.
    out_path = os.path.join(out_dir, "experiment_runs.csv")
    rows = []
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for fut in asyncio.as_completed(tasks):
            row = await fut
            w.writerow(row)
            fh.flush()
            rows.append(row)

    errors = sum(1 for r in rows if r["is_error"])
    capped = sum(1 for r in rows if r["hit_token_cap"])
    log.info("Wrote %d rows to %s", len(rows), out_path)
    log.info("  provider errors: %d   hit max_tokens: %d", errors, capped)
    if errors:
        log.warning("Exclude is_error rows — that is placeholder text, not a response.")
    if capped:
        log.warning("%d responses hit the token cap; their length is censored. "
                    "Raise max_tokens or exclude them from length measures.", capped)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--papers", type=int, default=5, help="papers to run (default 5)")
    ap.add_argument("--reps", type=int, default=3, help="replicates per cell (default 3)")
    ap.add_argument("--out", default="experiment", help="output directory")
    ap.add_argument("--reuse-papers", default=None, metavar="PATH",
                    help="papers.json from a previous run, so a backfilled "
                         "model sees the identical stimuli")
    ap.add_argument("--models", default=None,
                    help="comma-separated subset, e.g. claude,gpt,grok "
                         "(default: all four)")
    args = ap.parse_args()

    try:
        config = Config()
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        sys.exit(1)

    only = [m.strip() for m in args.models.split(",")] if args.models else None
    asyncio.run(run(config, args.papers, args.reps, args.out, only,
                    args.reuse_papers))


if __name__ == "__main__":
    main()
