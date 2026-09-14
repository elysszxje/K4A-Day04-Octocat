from __future__ import annotations

import json
import os
from typing import Any

from providers.base import ModelResponse, ToolCall


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        import re
        import time

        max_retries = 5
        resp = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                err_str = str(exc)
                if ("429" in err_str or "RateLimitError" in type(exc).__name__ or "rate_limit_exceeded" in err_str) and attempt < max_retries:
                    delay = 2.0 * attempt
                    match = re.search(r"try again in (\d+(\.\d+)?)s", err_str)
                    if match:
                        delay = max(delay, float(match.group(1)) + 0.5)
                    print(f"  [OpenAIProvider] TPM rate limit touched. Sleeping {delay:.1f}s before retry...", flush=True)
                    time.sleep(delay)
                else:
                    raise

        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)
