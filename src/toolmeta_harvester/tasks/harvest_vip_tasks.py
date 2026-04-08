import logging
import json
import requests
import subprocess
from pathlib import Path
from toolmeta_models import ToolGeneric
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from toolmeta_harvester.db.engine import engine
import toolmeta_harvester.db.science_file_types as sft

logger = logging.getLogger(__name__)

VIP_INDEX_URL = "https://vip.creatis.insa-lyon.fr/rest/pipelines?public"
BASE_URI = "https://vip.creatis.insa-lyon.fr/rest/pipelines/"
REPO_URL ="https://github.com/virtual-imaging-platform/vip-apps-boutiques-descriptors"
LOCAL_DIR = Path("cache/vip-apps-boutiques-descriptors")

def get_vip_index():
    try:
        response = requests.get(VIP_INDEX_URL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch VIP index: {e}")
        return None

def run_git_command(args, cwd=None):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git error: {result.stderr}")
    return result.stdout

def ensure_repo():
    if LOCAL_DIR.exists():
        logger.info("Repo exists → pulling latest changes")
        run_git_command(["pull"], cwd=LOCAL_DIR)
    else:
        logger.info("Cloning repo")
        run_git_command(["clone", REPO_URL, str(LOCAL_DIR)])

def get_repo_info():
    url = REPO_URL.replace(".git", "")
    parts = url.split("/")
    owner, repo = parts[-2], parts[-1]
    branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=LOCAL_DIR)
    return owner.strip(), repo.strip(), branch.strip()

def build_git_url(owner, repo, branch, file_path):
    rel = file_path.relative_to(LOCAL_DIR).as_posix()
    return f"https://github.com/{owner}/{repo}/blob/{branch}/{rel}"

def url_exists(url):
    try:
        r = requests.head(url, timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False

def process_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")

def get_inputs(data):
    inputs = data.get("inputs", [])
    results = []
    for input in inputs:
        slot = {
            "id": input.get("id", ""),
            "name": input.get("name", ""),
            "description": input.get("description", ""),
            "type": (input.get("type") or "").lower(),
            "file_formats": []
        }
        if input.get("type") == "File":
            slot["file_formats"] = sft.extract_filetypes(input.get("description", ""))
        results.append(slot)
    return results

def get_outputs(data):
    outputs = data.get("output-files", [])
    results = []
    for output in outputs:
        results.append({
                        "id": output.get("id", ""),
                        "name": output.get("name", ""),
                        "description": output.get("description", ""),
                        "type": (output.get("type") or "").lower(),
                        "file_formats": [],
                        })
    return results


def get_app_metadata():
    results = {}

    app_index = get_vip_index()
    if not app_index:
        logger.error("No app index found, aborting.")
        return
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

def patch_tool(id, data, api_url, token, timeout=10):
    headers = {
        "Content-Type": "application/json",
    }
    if not token:
            return {
                "success": False,
                "status": 443,
                "error": "No Token provided"
            }

    headers["Authorization"] = f"Bearer {token}"

    try:
        tool_url = f"{api_url}{id}"
        response = requests.patch(
            tool_url,
            json=data,
            headers=headers,
            timeout=timeout
        )

        if response.status_code in (200, 201):
            return {
                "success": True,
                "status": response.status_code,
                "response": response.json() if response.content else None
            }
        else:
            return {
                "success": False,
                "status": response.status_code,
                "error": response.text
            }

    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e)
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
            logger.info(f"VIP tool with URI {tool["uri"]} already exists in generic table. Skipping insert.")
            return existing  # Already in DB → return it

        vip_generic = ToolGeneric(
            uri=tool.get("uri", ""),
            name=tool.get("name", ""),
            location=tool.get("location", ""),
            description=tool.get("description", ""),
            version=tool.get("version", ""),
            types=tool.get("types", []),
            tags=tool.get("tags", []),
            keywords=tool.get("keywords", []),
            license=tool.get("license", ""),
            # input_file_formats=tool.input_formats,
            # output_file_formats=tool.output_formats,
            input_file_descriptions=tool.get("input_file_descriptions", []),
            output_file_descriptions=tool.get("output_file_descriptions", []),
            input_slots=tool.get("input_slots", []),
            output_slots=tool.get("output_slots", []),
            raw_definition=tool.get("raw_definition", {}),
            # raw_metadata=tool.raw_metadata,
            # metadata_schema={},
            # metadata_type="boutique_descriptor",
            # # metadata_version=tool.raw_ga.get("format-version", "unknown"),
            # metadata_version=tool.raw_metadata.get("jsonapi", {}).get("version", "unknown"),
            created_by="harvester",
        )
        session.add(vip_generic)
        session.commit()
        session.flush()
        logger.info(f"Added VIP tool {tool["uri"]} to generic table with ID {vip_generic.id}")
        return vip_generic
    except IntegrityError as e:
        logger.warning(f"IntegrityError for workflow tool {tool["uri"]}: {e}")
        session.rollback()
        return None
    except Exception as e:
        logger.error(f"Error adding workflow {tool["uri"]} to generic table: {e}")
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
                "error": "No Token provided"
            }

    headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            api_url,
            json=data,
            headers=headers,
            timeout=timeout
        )

        if response.status_code in (200, 201):
            return {
                "success": True,
                "status": response.status_code,
                "response": response.json() if response.content else None
            }
        else:
            return {
                "success": False,
                "status": response.status_code,
                "error": response.text
            }

    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }
