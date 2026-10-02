import time

import requests
from transformers import AutoTokenizer


EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v2-moe"
EMBEDDING_API_MODEL = "nomic-embed-text-v2-moe"

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

MAX_TOKENS = 500
API_BATCH_SIZE = 16


_tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)


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
    """Embed texts using the Nomic embedding API.

    Texts are:
      - prefixed according to their retrieval role;
      - truncated to the model's token limit;
      - sent to the API in batches;
      - returned in the same order as the input.

    Use DOCUMENT_PREFIX for indexed documents and QUERY_PREFIX
    for search queries.
    """

    if not texts:
        return []

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )

    # Leave the prefix inside tokenisation so it counts towards
    # the model's context limit.
    prepared_texts = []

    for text in texts:
        prefixed = prefix + text

        tokens = _tokenizer.encode(
            prefixed,
            add_special_tokens=False,
            truncation=True,
            max_length=max_tokens,
        )

        prepared_texts.append(
            _tokenizer.decode(
                tokens,
                skip_special_tokens=True,
            )
        )

    vectors: list[list[float]] = []

    for start in range(0, len(prepared_texts), batch_size):
        batch = prepared_texts[start : start + batch_size]

        for attempt in range(retries):
            try:
                response = session.post(
                    api_url,
                    json={
                        "model": model,
                        "input": batch,
                    },
                    timeout=timeout,
                )

                response.raise_for_status()

                data = sorted(
                    response.json()["data"],
                    key=lambda item: item["index"],
                )

                if len(data) != len(batch):
                    raise RuntimeError(
                        f"Embedding API returned {len(data)} vectors "
                        f"for {len(batch)} inputs"
                    )

                vectors.extend(item["embedding"] for item in data)

                break

            except requests.RequestException:
                if attempt == retries - 1:
                    raise

                time.sleep(2**attempt)

    return vectors
