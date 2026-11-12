from __future__ import annotations

import json
import re
import time
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
    """OpenAI-compatible EGI chat client with bounded transient retries."""

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
        self.last_request_count = 0
        self.last_elapsed_seconds = 0.0
        if not self.api_key or self.api_key.casefold() in {"your_key", "changeme"}:
            raise ValueError("EGI LLM API key must be configured")

    def complete_json(self, system_prompt: str, user_prompt: str) -> LLMCompletion:
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
                            time.sleep(min(2**attempt, 8))
                            continue
                    if not response.ok:
                        raise RuntimeError(
                            f"EGI chat completion returned HTTP {response.status_code}"
                        )
                    content, actual_model = self._response_content(response)
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("EGI chat completion returned empty content")
                    return LLMCompletion(
                        data=self._parse_json(content),
                        requested_model=self.model,
                        actual_model=actual_model,
                        request_count=self.last_request_count,
                        elapsed_seconds=time.perf_counter() - started,
                    )
                except (requests.Timeout, requests.ConnectionError) as exc:
                    last_error = exc
                    if attempt == self.retries:
                        break
                    time.sleep(min(2**attempt, 8))
                except requests.RequestException as exc:
                    last_error = exc
                    if attempt == self.retries:
                        break
                    time.sleep(min(2**attempt, 8))
                finally:
                    if response is not None:
                        response.close()
            raise RuntimeError(
                f"EGI chat completion failed after {self.last_request_count} requests"
            ) from last_error
        finally:
            self.last_elapsed_seconds = time.perf_counter() - started

    @staticmethod
    def _response_content(response: requests.Response) -> tuple[str, str | None]:
        content_type = response.headers.get("Content-Type", "").casefold()
        if "text/event-stream" not in content_type:
            body = response.json()
            return body["choices"][0]["message"]["content"], body.get("model")

        chunks: list[str] = []
        actual_model: str | None = None
        for line in response.iter_lines(decode_unicode=True):
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            if not line or not line.startswith("data:"):
                continue
            event = line[5:].strip()
            if event == "[DONE]":
                break
            try:
                body = json.loads(event)
            except json.JSONDecodeError as exc:
                raise ValueError("Malformed EGI streaming response") from exc
            if isinstance(body.get("model"), str):
                actual_model = body["model"]
            choices = body.get("choices") or []
            if choices:
                part = (choices[0].get("delta") or {}).get("content")
                if isinstance(part, str):
                    chunks.append(part)
        return "".join(chunks), actual_model

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM response did not contain a JSON object")
            try:
                parsed = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError("LLM response contained malformed JSON") from exc
        if not isinstance(parsed, dict):
            raise TypeError("LLM response JSON must be an object")
        return parsed
