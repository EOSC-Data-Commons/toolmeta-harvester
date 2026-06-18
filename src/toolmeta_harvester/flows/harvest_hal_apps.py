import json
import logging
from pathlib import Path
import re
import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit
from sickle import Sickle
import requests

from toolmeta_harvester import config
from toolmeta_harvester.config import settings
from toolmeta_harvester.tasks import harvest_hal_tasks as hal

LOG_FILE = (
    settings.get("LOG_FILE")
    or settings.get("default.log_file")
    or "logs/tools.log"
)
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE)],
)

logger = logging.getLogger(__name__)

# Important: Ensure ending forward slash in API_URL for correct endpoint construction in post_json_to_registry
# Development API URL
API_URL = settings.get(
    "hal.api_url",
    "https://api.archives-ouvertes.fr/oai/hal/?verb=ListRecords&metadataPrefix=oai_datacite&set=collection:LINKED_RESEARCH_OUTPUTS",
)
# Production API URL
# API_URL = "https://dev.tools-registry.eosc-data-commons.eu/api/v1/tools/"
ZENODO_RECORD_API = settings.get("zenodo.record_api", "https://zenodo.org/api/records")


def extract_zenodo_record_id(doi):
    match = re.search(r"zenodo\.(\d+)", doi or "", flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def fetch_zenodo_metadata_record(doi):
    record_id = extract_zenodo_record_id(doi)
    if not record_id:
        return None

    response = requests.get(
        f"{ZENODO_RECORD_API}/{record_id}",
        headers={"Accept": "application/json"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def is_notebook_file(file_name):
    return (file_name or "").lower().endswith(".ipynb")


def is_zip_file(file_name):
    return (file_name or "").lower().endswith(".zip")


def _parse_central_directory_names_from_tail(tail_bytes, range_start, total_size):
    eocd_sig = b"PK\x05\x06"
    cdfh_sig = b"PK\x01\x02"

    eocd_pos = tail_bytes.rfind(eocd_sig)
    if eocd_pos < 0:
        return None

    if eocd_pos + 22 > len(tail_bytes):
        return None

    eocd = struct.unpack_from("<HHHHIIH", tail_bytes, eocd_pos + 4)
    total_entries = eocd[3]
    central_dir_size = eocd[4]
    central_dir_offset = eocd[5]

    # ZIP64 requires extra records; fall back to full download for reliability.
    if total_entries == 0xFFFF or central_dir_size == 0xFFFFFFFF or central_dir_offset == 0xFFFFFFFF:
        return None

    if central_dir_offset < range_start:
        return None

    cd_start = central_dir_offset - range_start
    cd_end = cd_start + central_dir_size
    if cd_start < 0 or cd_end > len(tail_bytes):
        return None

    names = []
    pos = cd_start
    while pos < cd_end:
        if pos + 46 > len(tail_bytes):
            return None

        if tail_bytes[pos:pos + 4] != cdfh_sig:
            return None

        header = struct.unpack_from("<4s6H3I5H2I", tail_bytes, pos)
        name_len = header[10]
        extra_len = header[11]
        comment_len = header[12]

        name_start = pos + 46
        name_end = name_start + name_len
        if name_end > len(tail_bytes):
            return None

        names.append(tail_bytes[name_start:name_end].decode("utf-8", errors="replace"))
        pos = name_end + extra_len + comment_len

    return names


def _get_zip_notebooks_without_full_download(file_url, tail_size=262144):
    try:
        head_resp = requests.head(file_url, allow_redirects=True, timeout=20)
        head_resp.raise_for_status()
    except requests.RequestException:
        return None

    accept_ranges = (head_resp.headers.get("Accept-Ranges") or "").lower()
    content_length = head_resp.headers.get("Content-Length")
    if "bytes" not in accept_ranges or not content_length:
        return None

    try:
        total_size = int(content_length)
    except ValueError:
        return None

    if total_size <= 0:
        return None

    range_start = max(0, total_size - tail_size)
    try:
        response = requests.get(
            file_url,
            headers={"Range": f"bytes={range_start}-{total_size - 1}"},
            timeout=30,
        )
        if response.status_code != 206:
            return None
    except requests.RequestException:
        return None

    names = _parse_central_directory_names_from_tail(response.content, range_start, total_size)
    if names is None:
        return None

    return [name for name in names if is_notebook_file(name)]


def get_zip_notebooks(file_url):
    if not file_url:
        return []

    zip_notebooks = _get_zip_notebooks_without_full_download(file_url)
    if zip_notebooks is not None:
        return zip_notebooks

    try:
        logger.debug(f"Range ZIP inspection unavailable for {file_url}; falling back to full download")
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            return [name for name in zf.namelist() if is_notebook_file(name)]
    except (requests.RequestException, zipfile.BadZipFile) as e:
        logger.warning(f"Failed to inspect zip file {file_url}: {e}")
        return []


def _decode_text_bytes(raw_bytes):
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("utf-8", errors="replace")


def get_notebook_content(file_url):
    if not file_url:
        return ""

    try:
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        return response.json()
        # text = _decode_text_bytes(response.content)
        # return json.loads(text)
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch notebook content {file_url}: {e}")
        return ""


def get_zip_notebook_contents(file_url):
    if not file_url:
        return {}

    try:
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        contents = {}
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            for name in zf.namelist():
                if not is_notebook_file(name):
                    continue
                try:
                    contents[name] = _decode_text_bytes(zf.read(name))
                except KeyError:
                    logger.warning(f"Notebook entry {name} not found in zip: {file_url}")
        return contents
    except (requests.RequestException, zipfile.BadZipFile) as e:
        logger.warning(f"Failed to extract notebook content from zip {file_url}: {e}")
        return {}


def get_input_descriptions(data):
    inputs = data.get("inputs", [])
    descriptions = []
    for inp in inputs:
        if inp.get("type") == "File":
            desc = inp.get("description", "").lower()
            descriptions.append(desc)
    return descriptions

def get_output_descriptions(data):
    outputs = data.get("output-files", [])
    descriptions = []
    for out in outputs:
        desc = out.get("description", "").lower()
        descriptions.append(desc)
    return descriptions

def get_tools(api_url):
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch tools: {e}")
        return []

def harvest_hal_using_postgres_backend():
    session = hal.get_db_session()
    parsed_api = urlsplit(API_URL)
    oai_url = f"{parsed_api.scheme}://{parsed_api.netloc}{parsed_api.path}"
    query_params = parse_qs(parsed_api.query)
    metadata_prefix = query_params.get("metadataPrefix", ["oai_datacite"])[0]
    metadata_set = query_params.get("set", ["collection:LINKED_RESEARCH_OUTPUTS"])[0]
    sickle = Sickle(oai_url)
    records = sickle.ListRecords(metadataPrefix=metadata_prefix, set=metadata_set)

    ns = {
        "datacite": "http://datacite.org/schema/kernel-4",
    }
    seen_dois = set()
    zenodo_records = []
    logger.info("Processing records from HAL OAI-PMH endpoint...")
    tools = []
    saved_count = 0
    for i, record in enumerate(records, start=1):
        logger.debug(f"Processing record: {i}")
        # logger.info(f"Record {i}: {record}")
        doi_value = None
        try:
            root = ET.fromstring(str(record))
            doi_elem = root.find(
                ".//datacite:alternateIdentifier[@alternateIdentifierType='DOI']",
                ns,
            )
            if doi_elem is not None and doi_elem.text:
                doi_value = doi_elem.text.strip()
        except ET.ParseError as e:
            logger.warning(f"Unable to parse XML for record {i}: {e}")

        if doi_value and "/zenodo." in doi_value.lower() and doi_value not in seen_dois:
            seen_dois.add(doi_value)
            logger.debug(f"DOI {i}: {doi_value}")

            try:
                metadata = fetch_zenodo_metadata_record(doi_value)
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch Zenodo metadata for DOI {doi_value}: {e}")
                continue

            if metadata is None:
                logger.warning(f"Could not resolve Zenodo record ID for DOI {doi_value}")
                continue

            zenodo_records.append({"doi": doi_value, "metadata": metadata})
            rec_id = metadata.get("id", "unknown")
            logger.info(f"Zenodo record {rec_id} fetched for {doi_value}")
            files = metadata.get("files") or []
            if not files:
                logger.debug("  notebook files: []")
            else:
                printed_any = False
                for file_item in files:
                    file_name = file_item.get("key") or file_item.get("filename") or "unknown"
                    file_links = file_item.get("links") or {}
                    file_url = file_links.get("self") or file_links.get("download") or ""

                    if is_notebook_file(file_name):
                        if not printed_any:
                            logger.debug("  notebook files:")
                            printed_any = True
                        logger.debug(f"    - {file_name} {file_url}".rstrip())
                        logger.debug("--------------")
                        logger.debug(f"Record {i}: {record}")
                        logger.debug('---------------')
                        notebook_content = get_notebook_content(file_url)
                        if not notebook_content:
                            logger.debug(f"empty notebook: {file_name}")
                            continue
                        tool = set_tool_data(
                            {
                                "uri": (metadata.get("links") or {}).get("self") or f"{ZENODO_RECORD_API}/{rec_id}",
                                "name": (metadata.get("metadata") or {}).get("title") or file_name,
                                "version": (metadata.get("metadata") or {}).get("version") or metadata.get("version", ""),
                                "location": file_url,
                                "description": (metadata.get("metadata") or {}).get("description", ""),
                                "raw_metadata": metadata,
                                "raw_definition": notebook_content,
                                "metadata_type": "zenodo",
                            }
                        )
                        log_tool = {k: v for k, v in tool.items() if k not in {"raw_metadata", "raw_definition"}}
                        logger.debug(json.dumps(log_tool, indent=4, default=str))
                        tools.append(tool)
                        (saved_tool, saved) = hal.add_json_to_db(tool, session)
                        if saved:
                            saved_count += 1
                        continue

                    if is_zip_file(file_name):
                        zip_notebooks = get_zip_notebooks(file_url)
                        if zip_notebooks:
                            zip_notebook_contents = get_zip_notebook_contents(file_url)
                            if not printed_any:
                                logger.debug("  notebook files:")
                                printed_any = True
                            logger.debug(f"    - {file_name} {file_url}".rstrip())
                            for notebook_name in zip_notebooks:
                                logger.debug("=======")
                                logger.debug(f"Record {i}: {record}")
                                logger.debug('========')
                                notebook_content = zip_notebook_contents.get(notebook_name, "")
                                if not notebook_content:
                                    logger.debug(f"empty notebook: {notebook_name}")
                                    continue


                                tool = set_tool_data(
                                    {
                                        "uri": (metadata.get("links") or {}).get("self") or f"{ZENODO_RECORD_API}/{rec_id}",
                                        "name": (metadata.get("metadata") or {}).get("title") or notebook_name,
                                        "version": (metadata.get("metadata") or {}).get("version") or metadata.get("version", ""),
                                        "location": file_url,
                                        "description": (metadata.get("metadata") or {}).get("description", ""),
                                        "raw_metadata": metadata,
                                        "raw_definition": json.loads(notebook_content) if notebook_content else None,
                                        "metadata_type": "zenodo",
                                    }
                                )
                                log_tool = {k: v for k, v in tool.items() if k not in {"raw_metadata", "raw_definition"}}
                                logger.debug(json.dumps(log_tool, indent=4, default=str))
                                tools.append(tool)
                                (saved_tool, saved) = hal.add_json_to_db(tool, session)
                                if saved:
                                    saved_count += 1
                                logger.debug(f"      contains: {notebook_name}")

                if not printed_any:
                    logger.debug("  notebook files: []")

    logger.info(f"Collected {len(seen_dois)} unique Zenodo DOI(s)")
    logger.info(f"Fetched {len(zenodo_records)} Zenodo metadata record(s)")
    logger.info(f"Built {len(tools)} tool(s), saved {saved_count} to the database")
    return zenodo_records

    # apps = hal.get_app_metadata()
    # logger.info(f"Harvested {len(apps)} VIP apps")
    # counter = 0
    # for (name, version), tool in apps.items():
    #     logger.info(f"App: {name}, Version: {version}, URI: {tool['uri']}")
    #     logger.info(f"Input slots: {tool.get('input_slots', [])}")
    #     tool_from_db = hal.add_json_to_db(tool, session)
    #     if not tool_from_db:
    #         logger.error(f"Failed to add {name} version {version} to database")
    #         continue
    #     counter += 1
    # logger.info(f"Successfully added {counter} VIP apps to the database")

def set_tool_data(data=None):
    data = data or {}
    location = data.get("location")
    raw_definition = data.get("raw_definition")
    if raw_definition is None and is_notebook_file(location):
        raw_definition = get_notebook_content(location)
    if raw_definition is None:
        raw_definition = ""
    tool = {
        "uri": data.get("uri", None),
        "name": data.get("name", None),
        "version": data.get("version", None),
        "location": data.get("location", None),
        "types": data.get("types", ["python_notebook", "zenodo", "hal"]),
        "description": data.get("description", None),
        "input_file_formats": data.get("input_file_formats", []),
        "output_file_formats": data.get("output_file_formats", []),
        "input_file_descriptions": data.get("input_file_descriptions", []),
        "output_file_descriptions": data.get("output_file_descriptions", []),
        "raw_metadata": data.get("raw_metadata", {}),
        "metadata_version": data.get("metadata_version") or data.get("schema-version", ""),
        "raw_definition": raw_definition,
        "metadata_schema": data.get("metadata_schema", {}),
        "metadata_type": data.get("metadata_type", "zenodo"),

    }
    return tool

if __name__ == "__main__":
    harvest_hal_using_postgres_backend()
