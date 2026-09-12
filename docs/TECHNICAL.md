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

The historical error detector recognizes bracketed placeholder text. The candidate's replay utility preserves an existing `is_error` field rather than replacing a generation-time classification from a later text heuristic. Broader adapter-to-runner error handling still needs integration tests.

## Verification so far

Eight offline candidate checks cover syntax, replay metadata preservation, existing-output protection, request/stimulus validation, and selected Discord guards. Discord guard functions are executed with fakes rather than through a live SDK connection.

A separate private read-only record audit checks counts, duplicate keys, stored lengths, stimulus equivalence, and descriptive article-level contrasts. It prints aggregates without exporting responses. See [research notes](RESEARCH.md) for verified findings and remaining analysis gaps.

An isolated installation succeeded. Provider mocks, scheduler behavior, concurrent approval handling, and live-service compatibility still need checks before release. Model IDs are now supplied through environment configuration, and package build settings are explicit. No new provider calls were made during this review; a reviewed dependency lock and final installation guide are still pending.
