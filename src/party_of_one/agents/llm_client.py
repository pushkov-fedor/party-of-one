"""Shared LLM client utilities — API key loading and retry logic."""

from __future__ import annotations

import os
import time

from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError

from party_of_one.config import LLMConfig
from party_of_one.logger import get_logger

logger = get_logger()


def get_api_key() -> str:
    """Load OpenRouter API key from environment / .env file."""
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or key == "sk-or-replace-me":
        raise ValueError("OPENROUTER_API_KEY not set. Add it to .env file.")
    return key


def create_openrouter_client() -> OpenAI:
    """Create an OpenAI-compatible client pointing at OpenRouter."""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=get_api_key(),
        default_headers={"X-Title": "Party of One"},
    )


def call_with_retry(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: int,
    max_retries: int,
    agent_name: str,
    tools: list[dict] | None = None,
) -> object:
    """Call LLM API with exponential backoff retry."""
    last_error = None
    for attempt in range(max_retries):
        try:
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            logger.info(
                "llm_call",
                agent=agent_name,
                model=model,
                attempt=attempt + 1,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
            )
            return response
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning(
                "llm_retry",
                agent=agent_name,
                attempt=attempt + 1,
                error=str(e),
                wait_seconds=wait,
            )
            time.sleep(wait)

    raise RuntimeError(f"LLM API failed after {max_retries} retries: {last_error}")
