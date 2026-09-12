from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anthropic
import openai

if TYPE_CHECKING:
    from .config import Config, ModelConfig

log = logging.getLogger(__name__)

# Which token-limit parameter each model accepts, learned on first call.
_TOKEN_PARAM: dict[tuple[str, str | None, str], str] = {}

# One client per provider, reused. Constructing a client per call leaks its
# connection pool: a 120-generation run at CONCURRENCY=4 was found holding 18
# ESTABLISHED sockets and climbing, then stalled at 0% CPU with no progress for
# 50 minutes.
_CLIENTS: dict[tuple[str, str | None, str], object] = {}

# An explicit, short timeout matters more than the number itself. Without one, a
# request that never returns holds its semaphore slot forever; with only four
# slots, four such requests deadlock the entire run — which is what happened.
# Failing fast and retrying is strictly better than hanging: a retry costs
# seconds, a hang costs the run.
REQUEST_TIMEOUT_S = 120.0
MAX_RETRIES = 3

# Discord's per-message limit is 2000 characters. This is the bot's default
# ceiling; channels.py chunks anything longer rather than dropping it.
MAX_RESPONSE_LEN = 1900


@dataclass(frozen=True)
class Generation:
    """A response plus the facts you need to know whether it was cut short."""
    text: str
    finish_reason: str          # "stop" | "length" | "error" | provider value
    raw_chars: int              # length before any truncation of ours
    truncated_by_us: bool       # did max_len clip it
    # Extended thinking. None means "this provider does not report it", which
    # is not the same as zero.
    #
    # Presence and content are separate facts. Some recorded responses had
    # thinking blocks but no visible thinking text. Counting those blocks
    # from text length alone would incorrectly report absence.
    thinking_blocks: int | None = None
    thinking_chars: int | None = None   # None = present but not exposed

    # Optional provider-reported metadata, not a standardized measure of effort.
    # Missing fields stay None; availability depends on model and API settings.
    reasoning_tokens: int | None = None
    # Provider-returned reasoning text, if exposed. This is not evidence of
    # access to a model's complete internal reasoning.
    reasoning_text: str | None = None

    @property
    def had_thinking(self) -> bool | None:
        """Whether the response includes positive reasoning metadata, if known."""
        if self.reasoning_tokens is not None:
            return self.reasoning_tokens > 0
        return None if self.thinking_blocks is None else self.thinking_blocks > 0

    @property
    def hit_token_cap(self) -> bool:
        return self.finish_reason == "length"


async def generate(
    config: Config,
    model: ModelConfig,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2048,
) -> str:
    """Text only. The bot's entry point."""
    return (await generate_detailed(
        config, model, system_prompt, user_message, max_tokens
    )).text


async def generate_detailed(
    config: Config,
    model: ModelConfig,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2048,
    max_len: int | None = MAX_RESPONSE_LEN,
) -> Generation:
    """Generate a response, routing to the correct SDK.

    max_len=None disables our own truncation. The experiment passes None: the
    1900-char cut exists for Discord, and applying it to data written to CSV
    would censor response length, which is one of the measures.
    """
    try:
        if not model.model_id or not config.api_key_for(model.provider):
            raise ValueError("Configure a model ID and provider key before generation.")
        if model.provider == "anthropic":
            text, reason, extra = await _call_anthropic(
                config, model, system_prompt, user_message, max_tokens)
        else:
            text, reason, extra = await _call_openai_compat(
                config, model, system_prompt, user_message, max_tokens)
    except Exception as e:
        log.exception("Error calling %s: %s", model.name, e)
        return Generation(
            f"*[{model.display_name} is having a moment and couldn't respond: {type(e).__name__}]*",
            "error", 0, False)

    raw = len(text)
    if max_len is not None and raw > max_len:
        return Generation(text[:max_len], reason, raw, True, **extra)
    return Generation(text, reason, raw, False, **extra)


async def _call_anthropic(
    config: Config,
    model: ModelConfig,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
) -> tuple[str, str, dict]:
    client_key = ("anthropic", None, config.api_key_for("anthropic"))
    client = _CLIENTS.get(client_key)
    if client is None:
        client = _CLIENTS[client_key] = anthropic.AsyncAnthropic(
            api_key=config.api_key_for("anthropic"),
            timeout=REQUEST_TIMEOUT_S,
            max_retries=MAX_RETRIES,
        )
    response = await client.messages.create(
        model=model.model_id,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    # stop_reason: "end_turn" when it finished, "max_tokens" when it was cut off.
    reason = "length" if response.stop_reason == "max_tokens" else "stop"

    # Text need not be the first block. Historical debugging linked first-block
    # assumptions to pilot failures; the record audit alone cannot prove cause.
    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")

    # Count returned blocks separately from visible text. An empty thinking
    # field does not establish that no reasoning occurred.
    blocks = [b for b in response.content if getattr(b, "type", None) == "thinking"]
    chars = sum(len(getattr(b, "thinking", "") or "") for b in blocks)
    details = getattr(response.usage, "output_tokens_details", None)
    return text, reason if text.strip() else "error", {
        "thinking_blocks": len(blocks),
        "thinking_chars": chars if (chars or not blocks) else None,
        "reasoning_tokens": getattr(details, "thinking_tokens", None),
        "reasoning_text": None,   # this adapter does not store Anthropic thinking text
    }


async def _call_openai_compat(
    config: Config,
    model: ModelConfig,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
) -> tuple[str, str, dict]:
    client_key = (model.provider, model.base_url, config.api_key_for(model.provider))
    client = _CLIENTS.get(client_key)
    if client is None:
        kwargs: dict = {
            "api_key": config.api_key_for(model.provider),
            "timeout": REQUEST_TIMEOUT_S,
            "max_retries": MAX_RETRIES,
        }
        if model.base_url:
            kwargs["base_url"] = model.base_url
        client = _CLIENTS[client_key] = openai.AsyncOpenAI(**kwargs)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Newer OpenAI models reject max_tokens and require max_completion_tokens;
    # the OpenAI-compatible endpoints (Google, xAI) still implement the older
    # name. The SDK accepts both, so this can only be discovered from the
    # model's own 400 — try the widely-supported name and switch on that
    # specific rejection, remembering the answer per model.
    param_key = (model.provider, model.base_url, model.model_id)
    names = ([_TOKEN_PARAM[param_key]] if param_key in _TOKEN_PARAM
             else ["max_tokens", "max_completion_tokens"])
    response = None
    for i, param in enumerate(names):
        try:
            response = await client.chat.completions.create(
                model=model.model_id, messages=messages, **{param: max_tokens}
            )
            _TOKEN_PARAM[param_key] = param
            break
        except openai.BadRequestError as e:
            last = i == len(names) - 1
            if last or "max_completion_tokens" not in str(e):
                raise
            log.info("%s rejects max_tokens; using max_completion_tokens", model.name)
    choice = response.choices[0]
    text = choice.message.content or ""
    reason = choice.finish_reason or "stop"

    # Preserve optional vendor metadata without treating missing values as zero
    # or assuming that different providers measure the same thing.
    msg = choice.message
    cot = getattr(msg, "reasoning_content", None)
    if cot is None and getattr(msg, "model_extra", None):
        cot = msg.model_extra.get("reasoning_content") or msg.model_extra.get("reasoning")
    details = getattr(response.usage, "completion_tokens_details", None)
    extra = {
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "reasoning_text": cot or None,
    }

    if not text.strip():
        log.warning("%s returned no visible text (finish_reason=%s)", model.name, reason)
        return "", "error", extra
    return text, reason, extra
