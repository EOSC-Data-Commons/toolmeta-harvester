from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from xml.etree import ElementTree

import requests
from urllib.parse import urlparse

from toolmeta_harvester.db.models import HarvestResult
from toolmeta_harvester.flows.decorators import static_harvest


HAL_OAI_URL = "https://api.archives-ouvertes.fr/oai/hal/"
HAL_SET = "collection:LINKED_RESEARCH_OUTPUTS"
HAL_METADATA_PREFIX = "oai_datacite"

PIPELINE_VERSION = "0.1.0"

PIPELINE_TAG = (
    f"{__name__.rsplit('.', 1)[-1].removeprefix('harvest_')}@{PIPELINE_VERSION}"
)

REQUEST_TIMEOUT = (10, 60)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HalSwhRecord:
    oai_identifier: str
    swhid: str
    origin_url: str


def _local_name(tag: str) -> str:
    """
    Return the local part of an XML tag.

    {namespace}relatedIdentifier -> relatedIdentifier
    """
    return tag.rsplit("}", 1)[-1]


def extract_origin_url(swhid: str) -> str | None:
    """
    Extract the Software Heritage origin qualifier from an SWHID.

    Example:

        swh:1:dir:...;
        origin=https://github.com/data-fun/3d-genome-builder;
        visit=swh:1:snp:...;
        anchor=swh:1:rev:...

    returns:

        https://github.com/data-fun/3d-genome-builder
    """

    match = re.search(
        r"(?:^|;)origin=([^;]+)",
        swhid,
    )

    if not match:
        return None

    url = match.group(1).strip()

    if not url.startswith(("http://", "https://")):
        logger.warning(
            "Ignoring invalid SWH origin URL: %s",
            url,
        )
        return None

    return url


def extract_swh_records(xml: str) -> tuple[list[HalSwhRecord], str | None]:
    """
    Extract SWH related resources and the next OAI resumption token
    from one OAI-PMH response page.
    """

    root = ElementTree.fromstring(xml)

    records: list[HalSwhRecord] = []

    for record in root.iter():
        if _local_name(record.tag) != "record":
            continue

        header = next(
            (child for child in record if _local_name(child.tag) == "header"),
            None,
        )

        if header is None:
            continue

        # Ignore OAI records marked as deleted.
        if header.attrib.get("status") == "deleted":
            continue

        oai_identifier = next(
            (
                child.text
                for child in header
                if _local_name(child.tag) == "identifier" and child.text
            ),
            None,
        )

        if not oai_identifier:
            continue

        for element in record.iter():
            if _local_name(element.tag) != "relatedIdentifier":
                continue

            if element.attrib.get("relatedIdentifierType", "").upper() != "SWHID":
                continue

            if not element.text:
                continue

            swhid = element.text.strip()

            origin_url = extract_origin_url(swhid)

            if origin_url is None:
                logger.debug(
                    "SWHID in %s has no origin qualifier: %s",
                    oai_identifier,
                    swhid,
                )
                continue

            records.append(
                HalSwhRecord(
                    oai_identifier=oai_identifier,
                    swhid=swhid,
                    origin_url=origin_url,
                )
            )

    resumption_token = None

    for element in root.iter():
        if _local_name(element.tag) == "resumptionToken":
            if element.text and element.text.strip():
                resumption_token = element.text.strip()
            break

    return records, resumption_token


def iter_hal_swh_records():
    """
    Harvest all records from the HAL LINKED_RESEARCH_OUTPUTS
    collection using the DataCite OAI metadata representation.
    """

    params = {
        "verb": "ListRecords",
        "metadataPrefix": HAL_METADATA_PREFIX,
        "set": HAL_SET,
    }

    page = 1

    while True:
        logger.info(
            "Fetching HAL OAI page %d",
            page,
        )

        response = requests.get(
            HAL_OAI_URL,
            params=params,
            headers={
                "Accept": "application/xml",
            },
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        records, resumption_token = extract_swh_records(response.text)

        logger.info(
            "HAL OAI page %d: found %d SWH origins",
            page,
            len(records),
        )

        yield from records

        if not resumption_token:
            break

        # OAI-PMH requires subsequent requests to use only the
        # resumptionToken with the ListRecords verb.
        params = {
            "verb": "ListRecords",
            "resumptionToken": resumption_token,
        }

        page += 1


def normalize_origin_url(url: str) -> str:
    """
    Normalize HAL/SWH origin URLs into URLs understood by
    the existing harvest dispatcher.
    """

    url = url.strip()

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # DOI URL: keep it as DOI URL. Existing dispatcher can
    # resolve Zenodo DOI patterns.
    if hostname in {"doi.org", "dx.doi.org"}:
        return url

    # Git clone URLs
    if url.endswith(".git"):
        url = url[:-4]

    return url


@static_harvest(
    name="hal_swh",
    default_schedule="0 3 * * *",
)
def pipeline_harvest_hal_swh(
    limit: int | None = None,
) -> HarvestResult:
    """
    Discover software repository origins linked from HAL records
    through Software Heritage persistent identifiers.
    """

    origin_urls: list[str] = []
    failed_record_ids: list[str] = []

    seen: set[str] = set()

    for record in iter_hal_swh_records():
        if record.origin_url in seen:
            continue

        seen.add(record.origin_url)
        origin_urls.append(record.origin_url)

        logger.info(
            "HAL record %s -> %s",
            record.oai_identifier,
            record.origin_url,
        )

        if limit is not None and len(origin_urls) >= limit:
            break

    logger.info(
        "Found %d unique Software Heritage origins in HAL",
        len(origin_urls),
    )

    return HarvestResult(
        pipeline_tag=PIPELINE_TAG,
        record_ids=origin_urls,
        failed_record_ids=failed_record_ids,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract Software Heritage origin URLs from the "
            "HAL LINKED_RESEARCH_OUTPUTS OAI collection"
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    result = pipeline_harvest_hal_swh(
        limit=args.limit,
    )

    for url in result.record_ids:
        print(url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
