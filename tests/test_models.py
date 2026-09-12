"""Offline adapter regression tests: python -m unittest discover -s tests -v."""

import asyncio
import os
import socket
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import httpx
import openai

# Import the real configuration without consulting a local .env or credentials.
with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
    from src.config import Config, ModelConfig
    from src import models


def anthropic_response(blocks, stop_reason="end_turn", **usage):
    return NS(content=blocks, stop_reason=stop_reason, usage=NS(**usage))


def compat_response(text="answer", finish_reason="stop", usage=None, **message):
    return NS(
        choices=[NS(message=NS(content=text, **message), finish_reason=finish_reason)],
        usage=usage,
    )


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        models._CLIENTS.clear()
        models._TOKEN_PARAM.clear()
        self.addCleanup(models._CLIENTS.clear)
        self.addCleanup(models._TOKEN_PARAM.clear)
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.config = Config(
            anthropic_key="synthetic-anthropic", openai_key="synthetic-openai",
            google_key="synthetic-google", xai_key="synthetic-xai",
        )
        self.anthropic_model = ModelConfig("claude-test", "Test Claude", "fake-claude", "anthropic")
        self.compat_model = ModelConfig("gpt-test", "Test GPT", "fake-gpt", "openai")
        self.anthropic_call = AsyncMock()
        self.compat_call = AsyncMock()
        self.anthropic_factory = self.enterContext(patch.object(
            models.anthropic, "AsyncAnthropic",
            return_value=NS(messages=NS(create=self.anthropic_call)),
        ))
        self.compat_factory = self.enterContext(patch.object(
            models.openai, "AsyncOpenAI",
            return_value=NS(chat=NS(completions=NS(create=self.compat_call))),
        ))

    async def generate(self, model=None, **kwargs):
        return await models.generate_detailed(
            self.config, model or self.compat_model, "system", "question", **kwargs,
        )

    async def test_anthropic_mixed_blocks_preserve_text_order_and_metadata(self):
        self.anthropic_call.return_value = anthropic_response([
            NS(type="thinking", thinking="", signature="synthetic"),
            NS(type="text", text="first "),
            NS(type="tool_use"),
            NS(type="thinking", thinking="abc"),
            NS(type="text", text="second"),
        ], "max_tokens", output_tokens_details=NS(thinking_tokens=7))
        result = await self.generate(self.anthropic_model, max_tokens=123)
        self.assertEqual(result.text, "first second")
        self.assertEqual((result.thinking_blocks, result.thinking_chars, result.reasoning_tokens), (2, 3, 7))
        self.assertTrue(result.had_thinking)
        self.assertTrue(result.hit_token_cap)
        self.assertFalse(result.truncated_by_us)
        self.assertEqual(result.raw_chars, 12)
        self.assertIsNone(result.reasoning_text)
        self.anthropic_call.assert_awaited_once_with(
            model="fake-claude", max_tokens=123, system="system",
            messages=[{"role": "user", "content": "question"}],
        )

    async def test_anthropic_signature_only_thinking_has_unknown_length(self):
        self.anthropic_call.return_value = anthropic_response([
            NS(type="thinking", signature="synthetic", thinking=""),
            NS(type="text", text="answer"),
        ])
        result = await self.generate(self.anthropic_model)
        self.assertEqual(result.thinking_blocks, 1)
        self.assertIsNone(result.thinking_chars)
        self.assertIsNone(result.reasoning_tokens)
        self.assertTrue(result.had_thinking)

    async def test_anthropic_no_thinking_is_zero_not_unknown(self):
        self.anthropic_call.return_value = anthropic_response([NS(type="text", text="answer")])
        result = await self.generate(self.anthropic_model)
        self.assertEqual((result.thinking_blocks, result.thinking_chars), (0, 0))
        self.assertIsNone(result.reasoning_tokens)
        self.assertFalse(result.had_thinking)
        self.assertEqual(result.finish_reason, "stop")

    async def test_anthropic_empty_text_is_error(self):
        for blocks in ([], [NS(type="thinking", thinking="")], [NS(type="text", text=" \n")]):
            with self.subTest(blocks=blocks):
                self.anthropic_call.return_value = anthropic_response(blocks)
                result = await self.generate(self.anthropic_model)
                self.assertEqual(result.finish_reason, "error")
                self.assertFalse(result.text.strip())
                self.assertEqual(result.raw_chars, len(result.text))
                self.assertFalse(result.truncated_by_us)

    async def test_compat_metadata_and_provider_token_cap(self):
        self.compat_call.return_value = compat_response(
            "visible", "length", NS(completion_tokens_details=NS(reasoning_tokens=9)),
            reasoning_content="synthetic reasoning",
        )
        result = await self.generate(max_tokens=321)
        self.assertEqual(result.text, "visible")
        self.assertEqual(result.reasoning_tokens, 9)
        self.assertEqual(result.reasoning_text, "synthetic reasoning")
        self.assertTrue(result.had_thinking)
        self.assertTrue(result.hit_token_cap)
        self.assertFalse(result.truncated_by_us)
        self.compat_call.assert_awaited_once_with(
            model="fake-gpt", max_tokens=321,
            messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "question"}],
        )

    async def test_compat_missing_metadata_remains_unknown(self):
        for usage in (None, NS(), NS(completion_tokens_details=NS())):
            with self.subTest(usage=usage):
                self.compat_call.return_value = compat_response(usage=usage, finish_reason=None)
                result = await self.generate()
                self.assertIsNone(result.reasoning_tokens)
                self.assertIsNone(result.reasoning_text)
                self.assertIsNone(result.thinking_blocks)
                self.assertIsNone(result.thinking_chars)
                self.assertIsNone(result.had_thinking)
                self.assertEqual(result.finish_reason, "stop")

    async def test_compat_zero_tokens_and_extra_reasoning_fields(self):
        for field in ("reasoning_content", "reasoning"):
            with self.subTest(field=field):
                self.compat_call.return_value = compat_response(
                    usage=NS(completion_tokens_details=NS(reasoning_tokens=0)),
                    model_extra={field: "synthetic reasoning"},
                )
                result = await self.generate()
                self.assertEqual(result.reasoning_tokens, 0)
                self.assertFalse(result.had_thinking)
                self.assertEqual(result.reasoning_text, "synthetic reasoning")

    async def test_compat_empty_text_is_error_preserving_metadata(self):
        for text in (None, "", " \n\t"):
            with self.subTest(text=text):
                self.compat_call.return_value = compat_response(
                    text, "length", NS(completion_tokens_details=NS(reasoning_tokens=8)),
                    reasoning_content="synthetic reasoning",
                )
                with self.assertLogs(models.log, level="WARNING"):
                    result = await self.generate()
                self.assertEqual((result.text, result.finish_reason, result.raw_chars), ("", "error", 0))
                self.assertFalse(result.truncated_by_us)
                self.assertEqual(result.reasoning_tokens, 8)
                self.assertEqual(result.reasoning_text, "synthetic reasoning")

    async def test_max_len_clips_only_when_needed_and_none_preserves_all(self):
        for model, call, response in (
            (self.anthropic_model, self.anthropic_call, anthropic_response([NS(type="text", text="abcdef")])),
            (self.compat_model, self.compat_call, compat_response("abcdef")),
        ):
            call.return_value = response
            for limit, expected, clipped in ((3, "abc", True), (6, "abcdef", False), (None, "abcdef", False)):
                with self.subTest(provider=model.provider, limit=limit):
                    result = await self.generate(model, max_len=limit)
                    self.assertEqual((result.text, result.raw_chars, result.truncated_by_us), (expected, 6, clipped))
                    self.assertEqual(result.finish_reason, "stop")
                    self.assertFalse(result.hit_token_cap)

    async def test_default_limit_and_text_only_wrapper(self):
        text = "x" * (models.MAX_RESPONSE_LEN + 5)
        self.compat_call.return_value = compat_response(text)
        result = await self.generate()
        self.assertEqual(len(result.text), models.MAX_RESPONSE_LEN)
        self.assertEqual(result.raw_chars, len(text))
        self.assertTrue(result.truncated_by_us)
        self.assertEqual(await models.generate(self.config, self.compat_model, "system", "question"), result.text)

    async def test_sdk_exceptions_return_error_without_exception_detail(self):
        for model, call in ((self.anthropic_model, self.anthropic_call), (self.compat_model, self.compat_call)):
            with self.subTest(provider=model.provider):
                call.side_effect = RuntimeError("synthetic internal detail")
                with self.assertLogs(models.log, level="ERROR"):
                    result = await self.generate(model)
                self.assertEqual((result.finish_reason, result.raw_chars, result.truncated_by_us), ("error", 0, False))
                self.assertIn(model.display_name, result.text)
                self.assertIn("RuntimeError", result.text)
                self.assertNotIn("synthetic internal detail", result.text)

    async def test_missing_configuration_never_constructs_client(self):
        for model in (self.anthropic_model, self.compat_model):
            for missing in ("model", "key"):
                with self.subTest(provider=model.provider, missing=missing):
                    config = replace(self.config, anthropic_key="", openai_key="") if missing == "key" else self.config
                    selected = replace(model, model_id="") if missing == "model" else model
                    with self.assertLogs(models.log, level="ERROR"):
                        result = await models.generate_detailed(config, selected, "system", "question")
                    self.assertEqual(result.finish_reason, "error")
                    self.assertIn("ValueError", result.text)
        self.anthropic_factory.assert_not_called()
        self.compat_factory.assert_not_called()

    def bad_request(self, message):
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid/chat"))
        return openai.BadRequestError(message, response=response, body=None)

    async def test_token_parameter_fallback_is_cached(self):
        self.compat_call.side_effect = [
            self.bad_request("Use max_completion_tokens instead"),
            compat_response(), compat_response(),
        ]
        first = await self.generate(max_tokens=99)
        second = await self.generate(max_tokens=100)
        self.assertEqual((first.text, second.text), ("answer", "answer"))
        calls = [call.kwargs for call in self.compat_call.await_args_list]
        self.assertEqual(calls[0]["max_tokens"], 99)
        self.assertEqual(calls[1]["max_completion_tokens"], 99)
        self.assertEqual(calls[2]["max_completion_tokens"], 100)
        self.assertNotIn("max_tokens", calls[2])
        self.assertEqual(models._TOKEN_PARAM[("openai", None, "fake-gpt")], "max_completion_tokens")
        self.compat_factory.assert_called_once()

    async def test_unrelated_bad_request_does_not_retry(self):
        self.compat_call.side_effect = self.bad_request("Invalid model")
        with self.assertLogs(models.log, level="ERROR"):
            result = await self.generate()
        self.assertEqual(result.finish_reason, "error")
        self.compat_call.assert_awaited_once()
        self.assertFalse(models._TOKEN_PARAM)

    async def test_both_token_parameters_rejected_returns_error(self):
        self.compat_call.side_effect = self.bad_request("Unsupported max_completion_tokens")
        with self.assertLogs(models.log, level="ERROR"):
            result = await self.generate()
        self.assertEqual(result.finish_reason, "error")
        self.assertEqual(self.compat_call.await_count, 2)
        self.assertFalse(models._TOKEN_PARAM)

    async def test_provider_configuration_and_client_reuse(self):
        self.compat_call.return_value = compat_response()
        for provider, key in (("gemini", "synthetic-google"), ("grok", "synthetic-xai")):
            model = replace(self.compat_model, provider=provider, model_id="fake-" + provider, base_url="https://example.invalid/v1")
            await self.generate(model)
            await self.generate(model)
            self.compat_factory.assert_called_with(
                api_key=key, base_url="https://example.invalid/v1",
                timeout=models.REQUEST_TIMEOUT_S, max_retries=models.MAX_RETRIES,
            )
        self.assertEqual(self.compat_factory.call_count, 2)
        self.assertEqual(set(models._CLIENTS), {
            ("gemini", "https://example.invalid/v1", "synthetic-google"),
            ("grok", "https://example.invalid/v1", "synthetic-xai"),
        })

    async def test_experiment_row_preserves_adapter_error(self):
        from src import experiment

        model = replace(self.compat_model, name="gpt")
        paper = {"id": 1, "title": "Synthetic paper", "url": "https://example.invalid/paper", "content": "Synthetic content"}
        self.compat_call.return_value = compat_response(None)
        # _one calls the real adapter and measure function; only the SDK is fake.
        self.assertFalse(experiment.measure("", model.name)["is_error"])
        with self.assertLogs(models.log, level="WARNING"):
            row = await experiment._one(
                asyncio.Semaphore(1), self.config, model, "baseline", paper, 1, "synthetic-run",
            )
        self.assertTrue(row["is_error"])
        self.assertEqual(row["finish_reason"], "error")
        self.assertEqual(row["response"], "")
        self.assertEqual(row["reasoning_tokens"], "")


if __name__ == "__main__":
    unittest.main()
