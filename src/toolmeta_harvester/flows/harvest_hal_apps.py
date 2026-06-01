import logging
from pathlib import Path
import re
import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from sickle import Sickle
import requests

from toolmeta_harvester import config
from toolmeta_harvester.config import settings
from toolmeta_harvester.tasks import harvest_vip_tasks as vip

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
API_URL = "https://api.archives-ouvertes.fr/oai/hal/?verb=ListRecords&metadataPrefix=oai_datacite&set=collection:LINKED_RESEARCH_OUTPUTS"
# Production API URL
# API_URL = "https://dev.tools-registry.eosc-data-commons.eu/api/v1/tools/"
ZENODO_RECORD_API = "https://zenodo.org/api/records"


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
        logger.info(f"Range ZIP inspection unavailable for {file_url}; falling back to full download")
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            return [name for name in zf.namelist() if is_notebook_file(name)]
    except (requests.RequestException, zipfile.BadZipFile) as e:
        logger.warning(f"Failed to inspect zip file {file_url}: {e}")
        return []

def get_app_metadata():
    results = {}
    app_names = [app["name"] for app in app_index]
    logger.debug(f"Fetched VIP index with {len(app_index)} entries.")
    for folder in LOCAL_DIR.iterdir():
        if folder.is_dir():
            json_files = list(folder.glob("*.json"))

            if not json_files:
                logger.debug(f"No JSON files in {folder}")
                continue

            for json_file in json_files:
                data = process_json_file(json_file)
                if data is None:
                    continue
                if data.get("name") is None:
                    logger.warning(f"No 'name' field in {json_file}, skipping.")
                    continue
                if data.get("tool-version") is None:
                    logger.warning(f"No 'tool-version' field in {json_file}, skipping.")
                    continue
                name = data.get("name")
                version = data.get("tool-version")
                location = build_git_url(*get_repo_info(), json_file)
                if name in app_names:
                    logger.debug(f"App '{name}' found in VIP index.")
                    tool = {
                        "uri": f"{BASE_URI}{name}/{version}",
                        "name": name,
                        "version": version,
                        "location": location,
                        "types": ["boutique", "vip"],
                        "description": data.get("description", ""),
                        "input_file_formats": [],
                        "output_file_formats": [],
                        "input_file_descriptions": get_input_descriptions(data),
                        "output_file_descriptions": get_output_descriptions(data),
                        "input_slots": get_inputs(data),
                        "output_slots": get_outputs(data),
                        "raw_definition": data,
                        "raw_metadata": data,
                        "metadata_version": data.get("schema-version", ""),
                        "metadata_schema": {},
                        "metadata_type": "boutique_descriptor",

                    }
                    results[(name, version)] = tool
                else:
                    logger.warning(f"App '{name}' NOT found in VIP index.")
    return results

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
    session = vip.get_db_session()
    oai_url = "https://api.archives-ouvertes.fr/oai/hal"
    metadata_prefix = "oai_datacite"
    metadata_set = "collection:LINKED_RESEARCH_OUTPUTS"
    sickle = Sickle(oai_url)
    records = sickle.ListRecords(metadataPrefix=metadata_prefix, set=metadata_set)

    ns = {
        "datacite": "http://datacite.org/schema/kernel-4",
    }
    seen_dois = set()
    zenodo_records = []
    print("Processing records from HAL OAI-PMH endpoint...")
    tools = []
    for i, record in enumerate(records, start=1):
        print(f"Processing record: {i}")
        # print(f"Record {i}: {record}")
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
            print(f"DOI {i}: {doi_value}")

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
            print(f"Zenodo record {rec_id} fetched for {doi_value}")
            files = metadata.get("files") or []
            if not files:
                print("  notebook files: []")
            else:
                printed_any = False
                for file_item in files:
                    file_name = file_item.get("key") or file_item.get("filename") or "unknown"
                    file_links = file_item.get("links") or {}
                    file_url = file_links.get("self") or file_links.get("download") or ""

                    if is_notebook_file(file_name):
                        if not printed_any:
                            print("  notebook files:")
                            printed_any = True
                        print(f"    - {file_name} {file_url}".rstrip())
                        print("--------------")
                        print(f"Record {i}: {record}")
                        print('---------------')
                        continue

                    if is_zip_file(file_name):
                        zip_notebooks = get_zip_notebooks(file_url)
                        if zip_notebooks:
                            if not printed_any:
                                print("  notebook files:")
                                printed_any = True
                            print(f"    - {file_name} {file_url}".rstrip())
                            for notebook_name in zip_notebooks:
                                print("=======")
                                print(f"Record {i}: {record}")
                                print('========')
                                tool = set_tool_data()
                                tools.append(tool)
                                print(f"      contains: {notebook_name}")

                if not printed_any:
                    print("  notebook files: []")

    logger.info(f"Collected {len(seen_dois)} unique Zenodo DOI(s)")
    logger.info(f"Fetched {len(zenodo_records)} Zenodo metadata record(s)")
    return zenodo_records

    # apps = vip.get_app_metadata()
    # logger.info(f"Harvested {len(apps)} VIP apps")
    # counter = 0
    # for (name, version), tool in apps.items():
    #     logger.info(f"App: {name}, Version: {version}, URI: {tool['uri']}")
    #     logger.info(f"Input slots: {tool.get('input_slots', [])}")
    #     tool_from_db = vip.add_json_to_db(tool, session)
    #     if not tool_from_db:
    #         logger.error(f"Failed to add {name} version {version} to database")
    #         continue
    #     counter += 1
    # logger.info(f"Successfully added {counter} VIP apps to the database")

def set_tool_data(data):
    tool = {
        "uri": data.get("uri", ""),
        "name": data.get("name", ""),
        "version": data.get("version", ""),
        "location": data.get("location", ""),
        "archetype": "your_archetype_here",  # Replace with the appropriate archetype
        "description": data.get("description", ""),  # Replace with actual field name for description if different
        "input_file_formats": data.get("input_file_formats", []),
        # Replace with actual field name for input file formats if different
        "output_file_formats": data.get("output_file_formats", []),
        # Replace with actual field name for output file formats if different
        "input_file_descriptions": data.get("input_file_descriptions", []),
        # Replace with actual field name for input file descriptions if different
        "output_file_descriptions": data.get("output_file_descriptions", []),
        # Replace with actual field name for output file descriptions if different
        "raw_metadata": data,  # Store the original metadata for reference
        "metadata_version": data.get("schema-version", ""),
        # Replace with the actual field name for metadata version if different
        "metadata_schema": {},  # Replace with actual schema if available
        "metadata_type": "your_metadata_type_here",  # Replace with the appropriate metadata type

    }
    return tool

if __name__ == "__main__":
    harvest_hal_using_postgres_backend()
