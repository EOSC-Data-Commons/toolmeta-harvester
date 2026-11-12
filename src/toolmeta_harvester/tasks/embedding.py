from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

import requests

# Model tokenizer used to fit the embedding service's input limit.
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v2-moe"
EMBEDDING_API_MODEL = "nomic-embed-text-v2-moe"
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
MAX_TOKENS = 500
API_BATCH_SIZE = 16


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    requested_model: str
    actual_model: str | None
    request_count: int
    elapsed_seconds: float
    batches: list[dict[str, float | int]]


@lru_cache(maxsize=1)
def get_tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(EMBEDDING_MODEL)


def embed_with_metrics(
    texts: list[str],
    *,
    api_key: str,
    api_url: str,
    model: str = EMBEDDING_API_MODEL,
    prefix: str = DOCUMENT_PREFIX,
    max_tokens: int = MAX_TOKENS,
    batch_size: int = API_BATCH_SIZE,
    retries: int = 4,
    timeout: int = 120,
    session: requests.Session | None = None,
) -> EmbeddingResult:
    """Call the embedding API in batches and retain actual request metadata."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not texts:
        return EmbeddingResult([], model, None, 0, 0.0, [])

    started = time.perf_counter()
    tokenizer = get_tokenizer()
    prepared = []
    for text in texts:
        tokens = tokenizer.encode(
            prefix + text,
            add_special_tokens=False,
            truncation=True,
            max_length=max_tokens,
        )
        prepared.append(tokenizer.decode(tokens, skip_special_tokens=True))

    client = session or requests.Session()
    client.headers.update(
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    vectors: list[list[float]] = []
    actual_model: str | None = None
    request_count = 0
    batch_metrics: list[dict[str, float | int]] = []
    try:
        for start in range(0, len(prepared), batch_size):
            batch = prepared[start : start + batch_size]
            last_error: Exception | None = None
            batch_started = time.perf_counter()
            batch_requests = 0
            for attempt in range(retries + 1):
                request_count += 1
                batch_requests += 1
                response: requests.Response | None = None
                try:
                    response = client.post(
                        api_url,
                        json={"model": model, "input": batch},
                        timeout=timeout,
                    )
                    if (
                        response.status_code in {408, 429}
                        or response.status_code >= 500
                    ):
                        if attempt < retries:
                            time.sleep(min(2**attempt, 8))
                            continue
                    response.raise_for_status()
                    body = response.json()
                    data = sorted(body["data"], key=lambda item: item["index"])
                    if len(data) != len(batch):
                        raise RuntimeError(
                            f"Embedding API returned {len(data)} vectors for {len(batch)} inputs"
                        )
                    if isinstance(body.get("model"), str):
                        actual_model = body["model"]
                    vectors.extend(item["embedding"] for item in data)
                    batch_metrics.append(
                        {
                            "start": start,
                            "stop": start + len(batch),
                            "request_count": batch_requests,
                            "elapsed_seconds": time.perf_counter() - batch_started,
                        }
                    )
                    break
                except requests.RequestException as exc:
                    last_error = exc
                    if attempt == retries:
                        raise RuntimeError(
                            f"Embedding API failed after {request_count} requests"
                        ) from last_error
                    time.sleep(min(2**attempt, 8))
                finally:
                    if response is not None:
                        response.close()
            else:
                raise RuntimeError("Embedding request retry loop ended unexpectedly")
    finally:
        if session is None:
            client.close()

    return EmbeddingResult(
        vectors=vectors,
        requested_model=model,
        actual_model=actual_model,
        request_count=request_count,
        elapsed_seconds=time.perf_counter() - started,
        batches=batch_metrics,
    )


def embed(
    texts: list[str],
    *,
    api_key: str,
    api_url: str,
    model: str = EMBEDDING_API_MODEL,
    prefix: str = DOCUMENT_PREFIX,
    max_tokens: int = MAX_TOKENS,
    batch_size: int = API_BATCH_SIZE,
    retries: int = 4,
    timeout: int = 120,
) -> list[list[float]]:
    """Compatibility wrapper for callers that only need vectors."""
    return embed_with_metrics(
        texts,
        api_key=api_key,
        api_url=api_url,
        model=model,
        prefix=prefix,
        max_tokens=max_tokens,
        batch_size=batch_size,
        retries=retries,
        timeout=timeout,
    ).vectors
