from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from toolmeta_harvester.config import (
    egi_llm_api_key,
    egi_llm_api_url,
    egi_llm_model,
    llm_retries,
    llm_timeout,
)


@dataclass(frozen=True)
class LLMCompletion:
    data: dict[str, Any]
    requested_model: str
    actual_model: str | None
    request_count: int
    elapsed_seconds: float


class EgiChatClient:
    """OpenAI-compatible EGI client with bounded transient and malformed-response retries."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_url = api_url or egi_llm_api_url()
        self.api_key = api_key if api_key is not None else egi_llm_api_key()
        self.model = model or egi_llm_model()
        self.timeout = timeout if timeout is not None else llm_timeout()
        self.retries = retries if retries is not None else llm_retries()
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.last_request_count = 0
        self.last_elapsed_seconds = 0.0
        if not self.api_key or self.api_key.casefold().startswith("replace_"):
            raise ValueError("EGI LLM API key must be configured")
        if self.retries < 0 or self.timeout <= 0:
            raise ValueError(
                "LLM timeout must be positive and retries cannot be negative"
            )

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        validator: Callable[[dict[str, Any]], Any] | None = None,
    ) -> LLMCompletion:
        started = time.perf_counter()
        self.last_request_count = 0
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_error: Exception | None = None
        try:
            for attempt in range(self.retries + 1):
                response: requests.Response | None = None
                self.last_request_count += 1
                try:
                    response = self.session.post(
                        self.api_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0,
                            "stream": False,
                        },
                        timeout=self.timeout,
                    )
                    if (
                        response.status_code in {408, 429}
                        or response.status_code >= 500
                    ):
                        if attempt < self.retries:
                            self._backoff(attempt, response.headers.get("Retry-After"))
                            continue
                        raise RuntimeError(
                            f"EGI chat completion returned transient HTTP {response.status_code}"
                        )
                    if not response.ok:
                        raise RuntimeError(
                            f"EGI chat completion returned permanent HTTP {response.status_code}"
                        )
                    try:
                        content, actual_model = self._response_content(response)
                        if not isinstance(content, str) or not content.strip():
                            raise ValueError("Empty model response")
                        data = self._parse_json(content)
                        if validator is not None:
                            validated = validator(data)
                            data = (
                                validated.model_dump(mode="json")
                                if hasattr(validated, "model_dump")
                                else dict(validated)
                            )
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        last_error = exc
                        if attempt < self.retries:
                            self._backoff(attempt)
                            continue
                        raise RuntimeError(
                            "EGI chat completion returned an invalid JSON response"
                        ) from exc
                    return LLMCompletion(
                        data=data,
                        requested_model=self.model,
                        actual_model=actual_model,
                        request_count=self.last_request_count,
                        elapsed_seconds=time.perf_counter() - started,
                    )
                except (requests.Timeout, requests.ConnectionError) as exc:
                    last_error = exc
                    if attempt == self.retries:
                        break
                    self._backoff(attempt)
                except requests.RequestException as exc:
                    last_error = exc
                    if attempt == self.retries:
                        break
                    self._backoff(attempt)
                finally:
                    if response is not None:
                        response.close()
            raise RuntimeError(
                f"EGI chat completion failed after {self.last_request_count} request(s)"
            ) from last_error
        finally:
            self.last_elapsed_seconds = time.perf_counter() - started
            if self._owns_session:
                self.session.close()

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None = None) -> None:
        try:
            delay = (
                min(max(float(retry_after), 0), 30)
                if retry_after
                else min(2**attempt, 8)
            )
        except ValueError:
            delay = min(2**attempt, 8)
        time.sleep(delay + random.uniform(0, min(0.5, delay / 4)))

    @staticmethod
    def _response_content(response: requests.Response) -> tuple[str, str | None]:
        body = response.json()
        return body["choices"][0]["message"]["content"], body.get("model")

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE
        )
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM response did not contain a JSON object")
            parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise TypeError("LLM response JSON must be an object")
        return parsed
