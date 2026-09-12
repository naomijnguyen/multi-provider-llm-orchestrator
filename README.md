# Multi-Provider LLM Orchestrator

Journal Club started with a simple idea: put several models in a reading group and see what happens when they read the same material, take notes, and discuss it.

I built a Discord application around that idea, then added a separate experiment runner so I could compare prompt components more deliberately. Both use the same provider adapter. The application brings the models together; the experiment gives each model a first-response task without earlier model replies.

## What is here

- A Discord reading workflow with model-specific notes, discussion channels, scheduled runs, and draft preparation.
- A shared generation interface for Anthropic and OpenAI-compatible providers, with response text and completion metadata kept together.
- Four prompt conditions: shared task framing alone, with an identity anchor, with a persona, or with both.
- Saved stimuli and response rows, plus a separate utility for recalculating text measures without generating new responses.

## What I learned while building it

The pilot became a way to ask a second question: is this difference coming from the model, the prompt, or the instrument I built to collect and score the response?

Some calls failed unevenly across conditions. The historical debugging account traced that to a response parser that expected text in the first returned block. The first run records 24 Claude errors, including 14 in the persona-only condition. The Claude arm was then rerun against the same saved articles rather than mixing repaired calls into the earlier arm.

That is the part I want this project to show: something did not work, so the next step was to inspect the instrument. Parsing, output limits, error placeholders, and scoring rules can all change the apparent result. A pilot helps me find those problems while the experiment is still small enough to change.

That led to a clearer separation between the generation record and the measurements calculated from its text. It also gave me a better follow-up question: which prompt changes produce repeatable differences when the task stays the same?

The later release review found another useful example: a quoted sentence could be mistaken for a model identifying itself. That is a new review finding, not something I discovered during the original pilot. Keeping that timeline clear lets the project show how the testing continued after the first experiment.

The identity factor is specifically the added identity anchor. Persona prompts already name their models, so this is not a comparison between all identity cues and no identity cues. The reported historical pilot covers three models; four-provider support describes the application, not the pilot's sample.

## What the saved pilot shows

A read-only recount confirmed 359 non-error responses across ten saved articles. Within this stimulus set, the persona-present conditions had longer responses for Claude and GPT on every article. Grok's pattern was smaller and less consistent. These are descriptive observations about these prompts and articles, not a general ranking of models or proof of a mechanism.

[Research notes](docs/RESEARCH.md) explain the analysis set, calculations, and what changed in our interpretation.

## One implementation, two uses

The same provider adapter supports both the reading group and the experiment. The prompt components used by the application supply the experiment's conditions. The measurement function runs on fresh responses and can run again on saved text without paying for new generations.

That reuse is practical: the application gave me a place to notice behavior, and the experiment gave me a more controlled way to investigate it. [Architecture](docs/ARCHITECTURE.md) follows those shared modules; [technical notes](docs/TECHNICAL.md) describe their boundaries.

## Run and Explore

Start with the [local setup guide](docs/SETUP.md). The offline test suite uses synthetic provider responses, so you can check the adapters without accounts or API credits. Python dependencies are listed in `pyproject.toml`, with the tested versions in `constraints.txt`.

This source-inspection edition comes from the original Python implementation, with focused safety and data-preservation changes. The record audit confirms counts and descriptive length contrasts, not the historical inferential analysis.

Live generation spends provider tokens. Starting the Discord application connects to a server and can create channels and webhooks. Scheduled work now requires the owner's explicit `!club start` command. Neither entry point is an offline demo. No credentials or saved study data are included here.

Draft comments remain in Discord for manual review. External publishing code and credential settings are not included.

Read the project story on [Jennifer's portfolio](https://www.naomijnguyen.com/?doc=journal-club-evals).

## Rights and reuse

No open-source or general reuse license is granted for the original code and documentation in this repository. This is a portfolio source-inspection release. Third-party components retain their own licenses; provider names and logos belong to their respective owners and do not imply endorsement. Article text and historical response data are not bundled. Contact the author to discuss reuse permissions.
