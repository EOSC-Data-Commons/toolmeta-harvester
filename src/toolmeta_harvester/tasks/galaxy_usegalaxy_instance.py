
import logging
import requests
import requests_cache
import json
from pathlib import Path
from urllib.parse import urlparse
from toolmeta_harvester.tasks import galaxy_workflow as ga_workflow
import traceback

logger = logging.getLogger(__name__)

GALAXY_API = None
GALAXY_CACHE_FILE = None
GALAXY_DOMAIN = None

HEADERS = {
    "Accept": "application/json",
}


def set_galaxy_api_url(url):
    global GALAXY_API
    global GALAXY_CACHE_FILE
    global GALAXY_DOMAIN
    GALAXY_API = f"{url.rstrip('/')}/api"
    domain = urlparse(url).hostname
    GALAXY_CACHE_FILE = f"cache/{domain}_api_cache.json"
    # Initialize requests cache
    requests_cache.install_cache(
        f"cache/{domain}_request_cache", backend="sqlite", expire_after=86400
    )
    GALAXY_DOMAIN = domain

def get_json(url, result=None):
    if not result:
        result = []
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    result.extend(r.json())
    next_page = r.headers.get("next_page", None)
    if next_page:
        get_json(next_page, result)

    return result


def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)


def is_cached(filename):
    return Path(filename).is_file()

def get_ga_workflow(id):
    url = f"{GALAXY_API}/workflows/{id}/download?format=ga"
    request = requests.get(url, timeout=30, headers=HEADERS)
    request.raise_for_status()
    return request.json()

def iter_workflows():
    workflows = get_json(f"{GALAXY_API}/workflows")
    for wf in workflows:
        try:
            if wf.get("deleted", False):
                continue
            id = wf["id"]
            ga_w = get_ga_workflow(id)
            workflow_info = ga_workflow.parse_workflow(ga_w)
            workflow_info.url = f"{GALAXY_API}{wf['url']}"
            workflow_info.description = ga_w.get("annotation", "")
            workflow_info.version = ga_w.get("version", "")
            tags = wf.get("tags", [])
            license = ga_w.get("license", "")
            workflow_info.tags = tags if tags else []
            workflow_info.types = ["galaxy_workflow", GALAXY_DOMAIN]
            workflow_info.license = license if license else ""
            workflow_info.raw_ga = ga_w
            workflow_info.raw_metadata = wf
            workflow_info.metadata_type = GALAXY_DOMAIN
            
            yield workflow_info

        except Exception as e:
            logger.error(f"Error processing workflow {wf}: {e}")
            traceback.print_exc()
            continue
