from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from toolmeta_harvester.config import egi_llm_api_key, egi_llm_api_url, egi_llm_model


class EgiChatClient:
    """Small OpenAI-compatible EGI chat client with bounded transient retries."""

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
        self.timeout = timeout or int(os.environ.get("LLM_EGI_TIMEOUT", "180"))
        self.retries = (
            retries
            if retries is not None
            else int(os.environ.get("LLM_EGI_MAX_RETRIES", "3"))
        )
        self.session = session or requests.Session()
        if not self.api_key or self.api_key.casefold() in {"your_key", "changeme"}:
            raise ValueError("LLM_EGI_API_KEY must be configured")

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0,
                        "stream": True,
                    },
                    timeout=self.timeout,
                    stream=True,
                )
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self.retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                if not response.ok:
                    raise RuntimeError(
                        f"EGI chat completion returned HTTP {response.status_code}"
                    )
                content = self._response_content(response)
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("EGI chat completion returned empty content")
                return self._parse_json(content)
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
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Malformed EGI chat completion response") from exc

        raise RuntimeError(
            f"EGI chat completion failed after {self.retries + 1} attempts"
        ) from last_error

    @staticmethod
    def _response_content(response: requests.Response) -> str:
        content_type = response.headers.get("Content-Type", "").casefold()
        if "text/event-stream" not in content_type:
            body = response.json()
            return body["choices"][0]["message"]["content"]

        chunks: list[str] = []
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
            choices = body.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            part = delta.get("content")
            if isinstance(part, str):
                chunks.append(part)
        return "".join(chunks)

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
