# Run It Locally

Use Python 3.12 or newer. Start with the offline tests; they use synthetic responses and do not need accounts, tokens, Discord, or downloaded articles.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt .
python -m unittest discover -s tests -v
```

`constraints.txt` records the dependency versions used for the release checks on macOS with Python 3.12. It is a version snapshot, not a cross-platform or hash-verified lockfile. The project dependencies are listed in `pyproject.toml`.

## Configure a Live Run

Copy `.env.example` to `.env` in the folder you will run from. Fill in only the providers you plan to use, including their exact model IDs. The application deliberately ships without default model IDs or credentials. Keep your completed file private.

Live runs make paid provider calls. Model access and optional response metadata depend on your account and selected model. The tests check adapter behavior with mocks, not current service availability.

### Experiment Runner

The experiment does not need Discord. This example requests one article, one replicate in each of the four conditions, and one configured provider:

```sh
python -m src.experiment --papers 1 --reps 1 --models gpt --out outputs/pilot-001
```

The runner fetches public feeds unless you supply `--reuse-papers PATH` with a previously saved `papers.json`. Each run needs a new output folder so earlier results are not overwritten. Provider retries can add attempts beyond the planned generation count.

Keep saved article text and model responses private unless you have reviewed their content and rights. This repository includes neither the original study data nor a redistributed article collection. The published research notes contain aggregate results.

### Discord Reading Group

Use a dedicated server for testing. Configure the bot token, server ID, owner ID, and the four provider/model pairs. Enable the message-content intent for your bot and grant only the permissions needed to read/send messages, read history, and manage its channels and webhooks. Avoid granting Administrator.

```sh
models-only
```

Connecting prepares the channels. It does not start the scheduler. The configured owner can use `!club start`, `!club stop`, and `!club status`; `!scrape` and `!gossip` trigger work immediately. These actions can spend provider tokens. Stopping the schedule is not a hard billing cap or a guarantee that already-running calls are canceled.

Draft comments stay in Discord for manual review. This edition has no external comment-publishing module or credential setting.

## Recalculate Saved Text Measures

Use `python -m src.recompute PATH_TO_COPIED_CSV` to replay the text measures. Work on a copy: it updates the selected CSV in place. It does not call a model, and it preserves the original generation-error flag. The measures and their interpretation are described in [technical notes](TECHNICAL.md).
