# Version 0.1.0

The first public source-inspection release of Multi-Provider LLM Orchestrator, originally Journal Club.

## Included

- Discord reading, discussion, and draft-review workflows.
- Shared Anthropic and OpenAI-compatible provider adapters.
- A four-condition prompt-component experiment runner.
- Offline text-measure replay and aggregate pilot research notes.
- Local setup instructions, empty configuration template, and tested dependency versions.

## Release Checks

Twenty offline tests cover adapters, error propagation, metadata, and runtime safeguards. Eight additional preparation checks cover input validation, data preservation, syntax, and selected access guards. A clean Python 3.12 installation, dependency check, and package build passed.

The review did not make live model calls or connect to Discord. Historical pilot records remain separate from these synthetic release tests. Optional model metadata and account access need checking for any new live run.

## Public Edition Changes

Scheduled work requires an explicit owner command. External comment publishing and its credential settings have been removed. Generated messages cannot trigger Discord mentions. New experiment runs refuse existing output folders, and replay preserves recorded generation-error flags.

Client reuse is scoped to provider, endpoint, and credentials. Empty visible responses are errors, without an invented explanation for why text was absent. Provider-returned reasoning metadata stays distinct from claims about internal reasoning.

No credentials, databases, logs, article collection, or original response records are included. No general reuse license is granted for original material. See the README for rights and dependency attribution.
