# Calculation and Execution Notes

## Generation records

The adapter returns response text, completion reason, app truncation information, and available provider metadata. The runner disables the adapter's Discord-oriented character clipping with `max_len=None`. Provider token limits and the prompt's length instruction still apply.

Unknown reasoning metadata is distinct from zero. Provider-specific field availability and comparability need separate verification; do not infer cognition from missing metadata or assume all providers report the same quantity.

## Prompt and stimulus construction

Shared reading-task framing appears in every condition. Identity anchors and persona additions define the factorial contrast. The article body is truncated to 4,000 characters, and original/used lengths are recorded. This is positional truncation, not section-aware scientific article extraction.

The candidate validates positive paper/replicate counts, requested provider names, and basic reused-paper fields before generation. It rejects an existing output directory. Reused stimuli must contain `id`, `lw_id`, `title`, `url`, `author`, and `content`; authors and content may be null.

## Text measures

Measurements include character and token-like word counts, punctuation/formatting counts, paragraph/sentence heuristics, lexical diversity, and regex-based identity patterns. These are observable text features, not semantic correctness or internal-state measurements. Their token-like words are not provider tokenizer tokens.

The identity matcher recognizes common self-statements and opening bylines but can also match quoted statements. The candidate has not silently changed that detector. A reviewed annotation set is the next step before rescoring historical identity results.

The historical error detector recognizes bracketed placeholder text. The replay utility preserves an existing `is_error` field rather than replacing a generation-time classification from a later text heuristic. Fresh runs also use the adapter's error classification, so an empty visible response cannot silently become a successful measurement. An offline integration test covers that path.

## Verification

The public offline suite checks mixed response blocks, optional metadata, token-parameter fallback, client reuse, text clipping, error handling, generation-to-measurement propagation, disabled external publishing, and scheduler start/stop behavior. It imports the real application modules and replaces provider calls with synthetic responses. Run it with `python -m unittest discover -s tests -v`.

Eight additional preparation checks cover syntax, replay metadata preservation, existing-output protection, request/stimulus validation, and selected Discord guards.

A separate private read-only record audit checks counts, duplicate keys, stored lengths, stimulus equivalence, and descriptive article-level contrasts. It prints aggregates without exporting responses. See [research notes](RESEARCH.md) for verified findings and remaining analysis gaps.

An isolated installation and wheel build succeeded. The [setup guide](SETUP.md) includes a tested dependency snapshot. Model IDs come from environment configuration. The release review made no live provider calls or Discord connections; mocks establish the tested code paths, not current model access or end-to-end live-service compatibility. External publishing has been removed, so there is no comment-approval publishing race in this edition.
