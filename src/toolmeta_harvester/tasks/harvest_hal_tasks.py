import logging
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import requests
from toolmeta_models import ToolGeneric

from toolmeta_harvester.config import settings
from toolmeta_harvester.db.engine import engine

logger = logging.getLogger(__name__)

HAL_API_URL = settings.get(
    "hal.api_url",
    "https://api.archives-ouvertes.fr/oai/hal/?verb=ListRecords&metadataPrefix=oai_datacite&set=collection:LINKED_RESEARCH_OUTPUTS",
)
ZENODO_RECORD_API = settings.get("zenodo.record_api", "https://zenodo.org/api/records")


def get_tools(api_url):
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error(f"Failed to fetch tools: {exc}")
        return []


def patch_tool(tool_id, data, api_url, token, timeout=10):
    headers = {
        "Content-Type": "application/json",
    }
    if not token:
        return {
            "success": False,
            "status": 403,
            "error": "No Token provided",
        }

    headers["Authorization"] = f"Bearer {token}"

    try:
        tool_url = f"{api_url}{tool_id}"
        response = requests.patch(
            tool_url,
            json=data,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code in (200, 201):
            return {
                "success": True,
                "status": response.status_code,
                "response": response.json() if response.content else None,
            }

        return {
            "success": False,
            "status": response.status_code,
            "error": response.text,
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def get_db_session():
    return Session(engine)


def add_json_to_db(tool, session=None):
    if not session:
        session = Session(engine)

    try:
        existing = session.execute(
            select(ToolGeneric).where(ToolGeneric.uri == tool["uri"])
        ).scalar_one_or_none()

        if existing:
            logger.info(
                f"HAL tool with URI {tool['uri']} already exists in generic table. Skipping insert."
            )
            return existing

        hal_generic = ToolGeneric(
            uri=tool.get("uri", ""),
            name=tool.get("name", ""),
            location=tool.get("location", ""),
            description=tool.get("description", ""),
            version=tool.get("version", ""),
            types=tool.get("types", []),
            tags=tool.get("tags", []),
            keywords=tool.get("keywords", []),
            license=tool.get("license", ""),
            input_file_descriptions=tool.get("input_file_descriptions", []),
            output_file_descriptions=tool.get("output_file_descriptions", []),
            input_slots=tool.get("input_slots", []),
            output_slots=tool.get("output_slots", []),
            raw_definition=tool.get("raw_definition", {}),
            created_by="harvester",
        )

        session.add(hal_generic)
        session.commit()
        session.flush()

        logger.info(
            f"Added HAL tool {tool['uri']} to generic table with ID {hal_generic.id}"
        )
        return hal_generic
    except IntegrityError as exc:
        logger.warning(f"IntegrityError for HAL tool {tool['uri']}: {exc}")
        session.rollback()
        return None
    except Exception as exc:
        logger.error(f"Error adding HAL tool {tool['uri']} to generic table: {exc}")
        session.rollback()
        raise


def post_json_to_registry(data, api_url, token=None, timeout=10):
    headers = {
        "Content-Type": "application/json",
    }

    if not token:
        return {
            "success": False,
            "status": 403,
            "error": "No Token provided",
        }

    headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            api_url,
            json=data,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code in (200, 201):
            return {
                "success": True,
                "status": response.status_code,
                "response": response.json() if response.content else None,
            }

        return {
            "success": False,
            "status": response.status_code,
            "error": response.text,
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "error": str(exc),
        }

