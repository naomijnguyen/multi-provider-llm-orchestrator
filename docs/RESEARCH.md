# Pilot, Instrument, and Next Experiment

## The question

What changes when the same reading task is paired with an identity anchor, a model-specific persona, or both? The pilot crossed two prompt components while retaining the shared task framing. It collected first responses, not multi-turn discussions.

The identity-anchor factor adds a particular instruction block. Persona prompts already name the model. This is a prompt-composition comparison, not identity versus no identity in every cell.

## What we checked in the records

A read-only September 12 review of the original and rerun CSVs confirmed:

- The initial file contains 360 rows: 120 each for Claude, GPT, and Grok.
- Recorded errors include 24 Claude rows and one Grok row. Claude errors are distributed 0 / 5 / 14 / 5 across baseline / identity-only / persona-only / full.
- The rerun contains 120 Claude rows with no recorded errors. Its ten parsed stimulus records exactly match the original saved set.
- Combining initial GPT/Grok with rerun Claude gives 359 non-error rows. Gemini is not present in these result files.
- Neither file has duplicate model/article/condition/replicate keys. Stored character counts match response lengths. No combined non-error row is marked as hitting the token cap; that verifies the recorded flags, not the original provider response payloads.

The saved responses and article text remain private. This document reports aggregates, not a public release of the corpus.

## What we measured

The runner saves response length, word-like counts, sentence and paragraph heuristics, formatting and punctuation counts, lexical diversity, and regex-based identity claims. These describe the visible response; they do not score whether its argument is correct. Generation metadata is stored separately from those text measurements.

The initial 360-row file has no populated thinking or reasoning metadata in the fields inspected. The Claude rerun records thinking-block presence on 10 of 120 responses. Those ten rows leave thinking character counts blank; the other 110 record zero. Neither file contains populated reasoning text or reasoning-token counts. A blank field means unavailable, not zero, and the ten returned-block observations are separate from the earlier 24 parser errors.

## Response length in the saved pilot

For each article and model, average response character counts within each condition. Compute the persona contrast as:

`((persona_only + full) - (baseline + identity_only)) / 2`

Then average these contrasts equally across the ten articles.

| Model | Mean contrast, characters | Articles with a positive contrast | Range across articles |
| --- | ---: | ---: | ---: |
| Claude | +190.45 | 10/10 | +61.67 to +289.17 |
| GPT | +119.70 | 10/10 | +66.83 to +180.83 |
| Grok | +40.58 | 8/10 | -5.67 to +137.83 |

The Grok persona-only cell has one missing response. Equal-article weighting produces +40.58; applying the contrast to pooled condition means produces about +42.91. This explains why a rounded +43 and a differently weighted estimate can coexist. Always name the weighting rule.

These are observations within ten selected articles, not ten independent replications of an entire study or a population-wide estimate. Repeated generations describe sampling variation within the same article/condition. Persona content and prompt length change together, so longer responses do not identify which component caused the change.

## What the pilot taught us about the instrument

The historical debugging notes attribute uneven Claude failures to assuming the first returned block was text. The retained records confirm the failure distribution and replacement run; the current parser selects text blocks by type. Together these support the debugging account, but the records reviewed here do not independently replay the original exception.

The important decision was to examine missingness by condition and replace the affected arm using the same stimuli. The replacement run also occurred later, so time is not controlled between every provider arm.

The original identity detector was revised after missing byline forms. Our later review reproduced a different issue: quoted identity statements can be false positives. Both illustrate why a measurement needs examples where the expected answer is known. The new finding should not be backdated into the pilot story.

## Interpretations we are not carrying forward as established results

- Previously reported permutation p-values, standardized effects, split-half reliability, and variance decompositions have not been reproduced in this review. No standalone analysis script for those calculations was found in the inspected project files.
- A corrected correlation above 1 does not establish perfect agreement. Preserve the observed estimates and investigate uncertainty and assumptions before interpreting the correction.
- A non-monotonic condition pattern does not exclude prompt length or isolate a mechanism.
- Failure on a returned thinking block is an indirect parser-event observation, not a general measure of whether a model reasoned. Missing provider metadata must remain unknown.
- A small p-value is not automatically protected against multiple comparisons. Specify the test family and correction before making confirmatory claims.

## What I would do next

Use a frozen stimulus set, test scoring rules against annotated examples, retain generation metadata separately from recalculated measures, and specify the analysis before another run. An immunology corpus would give me material I can assess directly. A multi-turn study would need recorded speaking order and peer context because those are part of the input, not background details.

The Study 2 notes are a proposed protocol. The current runner does not implement that entire follow-up. The payoff of this pilot is a better instrument and a more precise next question.
