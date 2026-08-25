import html
import re
from typing import Any

from bs4 import BeautifulSoup


def clean_description(value: Any) -> str:
    """
    Convert a potentially dirty description into clean plain text.

    Intended for descriptions that may contain:
    - HTML
    - Markdown
    - code fences
    - inline code
    - Markdown links/images
    - HTML entities
    - excessive whitespace

    The result is suitable for search indexing and embeddings.
    """

    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    text = value.strip()

    if not text:
        return ""

    text = decode_html_entities(text)
    text = remove_code_blocks(text)
    text = remove_markdown_images(text)
    text = convert_markdown_links(text)
    text = strip_html(text)
    text = strip_markdown(text)
    text = normalize_whitespace(text)

    return text.strip()


def decode_html_entities(text: str) -> str:
    """
    Decode entities such as &amp;, &lt;, &nbsp;, etc.
    """

    return html.unescape(text)


def strip_html(text: str) -> str:
    """
    Remove HTML while preserving visible text.
    """

    soup = BeautifulSoup(text, "html.parser")

    # Remove content that should not contribute semantic text.
    for element in soup(["script", "style", "noscript", "svg", "iframe"]):
        element.decompose()

    return soup.get_text(separator=" ")


def remove_code_blocks(text: str) -> str:
    """
    Remove fenced Markdown code blocks.

    Code is usually noise for description embeddings. If source code
    is important, it should be embedded/indexed separately.
    """

    text = re.sub(
        r"```.*?```",
        " ",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"~~~.*?~~~",
        " ",
        text,
        flags=re.DOTALL,
    )

    return text


def remove_markdown_images(text: str) -> str:
    """
    Remove Markdown images while retaining alt text where available.

    ![workflow diagram](image.png)

    becomes:

    workflow diagram
    """

    return re.sub(
        r"!\[([^\]]*)\]\([^)]+\)",
        r"\1",
        text,
    )


def convert_markdown_links(text: str) -> str:
    """
    Keep Markdown link labels but discard their URLs.

    [WorkflowHub](https://workflowhub.eu)

    becomes:

    WorkflowHub
    """

    return re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text,
    )


def strip_markdown(text: str) -> str:
    """
    Remove common Markdown formatting while preserving its text.
    """

    # Headings
    text = re.sub(
        r"(?m)^\s{0,3}#{1,6}\s+",
        "",
        text,
    )

    # Block quotes
    text = re.sub(
        r"(?m)^\s*>\s?",
        "",
        text,
    )

    # Horizontal rules
    text = re.sub(
        r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$",
        " ",
        text,
    )

    # List markers
    text = re.sub(
        r"(?m)^\s*[-*+]\s+",
        "",
        text,
    )

    # Numbered list markers
    text = re.sub(
        r"(?m)^\s*\d+[.)]\s+",
        "",
        text,
    )

    # Inline code
    text = re.sub(
        r"`([^`]+)`",
        r"\1",
        text,
    )

    # Bold / italic
    text = re.sub(
        r"\*\*([^*]+)\*\*",
        r"\1",
        text,
    )

    text = re.sub(
        r"__([^_]+)__",
        r"\1",
        text,
    )

    text = re.sub(
        r"\*([^*]+)\*",
        r"\1",
        text,
    )

    text = re.sub(
        r"_([^_]+)_",
        r"\1",
        text,
    )

    # Strikethrough
    text = re.sub(
        r"~~([^~]+)~~",
        r"\1",
        text,
    )

    return text


def normalize_whitespace(text: str) -> str:
    """
    Collapse repeated whitespace and blank lines into normal spaces.
    """

    text = text.replace("\xa0", " ")

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()
