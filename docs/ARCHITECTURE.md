# Shared Modules, Different Workflows

## Reading group

`main.py` configures the Discord bot. `scheduler.py` schedules work, `scraper.py` collects posts, and `db.py` stores application state. `bot.py` assembles reading/discussion prompts and uses `models.py` for generation. `channels.py` presents outputs through Discord channels and model-specific webhooks.

Model-specific note channels separate the prompts and outputs. The code does not itself establish per-model private Discord permissions; channel access depends on server/category configuration.

## Pilot experiment

`experiment.py` reuses `models.py` but does not start Discord. `conditions.py` composes four conditions from `personas.py`. Each request receives an article excerpt and a first-response task. `measures.py` calculates text measures, and the runner writes each completed response with its condition and generation metadata.

The experiment can reuse saved article records rather than scrape changing feeds. Its scratch database is separate from the configured club database. The candidate requires a new output directory, protecting prior runs from accidental replacement.

## Offline analysis

`recompute.py` reuses `measures.py` on saved responses. It makes no generation calls. The candidate preserves recorded error flags while updating eligible text-derived columns. Recalculation replaces the specified CSV, so work on a copy when preserving historical measurements matters.

## Where reuse is concrete

| Module | Application use | Research use |
| --- | --- | --- |
| `models.py` | Generate model contributions | Generate labeled experimental responses |
| `personas.py` | Supply channel voices and identity anchors | Supply components for prompt conditions |
| `measures.py` | Not automatically called by the Discord exporter | Score fresh responses and rescore saved text |
| `scraper.py`, `db.py` | Collect and retain club posts | Prepare a separate scratch stimulus collection |

The shared code creates opportunities for comparison, not automatic equivalence: the bot includes peer context and presentation limits, while the experiment requests uncropped first responses.

## Side effects and boundaries

Discord startup can create channels and webhooks. Scheduled provider calls require the owner's explicit `!club start` command. The candidate requires a configured owner and checks server/channel identity. External draft posting is off by default and remains under review. These are separate from the portfolio site's assistant and passphrase system.

Historical data, credentials, and original Git history are not part of the candidate. No new web application or production backend has been added for the portfolio.
