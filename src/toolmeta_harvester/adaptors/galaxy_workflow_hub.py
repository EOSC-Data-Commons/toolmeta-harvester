import logging
import requests
import requests_cache
import json
from pathlib import Path
import zipfile
import io
from toolmeta_harvester.adaptors import galaxy_workflow as ga_workflow

logger = logging.getLogger(__name__)

TOOLShed = "https://toolshed.g2.bx.psu.edu"
WORKFLOW_HUB_API = "https://workflowhub.eu/ga4gh/trs/v2/"
HUB_CACHE_FILE = "cache/workflowhub_registry.json"

HEADERS = {
    "Accept": "application/json",
}

# Initialize requests cache 
requests_cache.install_cache('cache/workflowhub_org_cache', 
                             backend='sqlite',
                             expire_after=86400)

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

def fetch_text_file(url):
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    return r.text

def retrieve_json(url, cache_file, use_cache=True):
    if use_cache and is_cached(cache_file):
        print("Loading registry from cache...")
        return load_json(cache_file)
    workflows = get_json(url)
    save_json(workflows, cache_file)
    return workflows

# Extract Galaxy workflow from ZIP file at given URL
def extract_galaxy_workflow_from_zip(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # Open ZIP in memory
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        ga_files = [name for name in zf.namelist() if name.endswith(".ga")]

        if not ga_files:
            raise ValueError("No .ga Galaxy workflow file found in ZIP")

        # Take the first .ga file
        ga_name = ga_files[0]

        with zf.open(ga_name) as ga_file:
            return json.load(ga_file)

# Get workflows from Workflow Hub, optionally filtering by type
def get_hub_workflows(type=None):
    workflows = retrieve_json(f"{WORKFLOW_HUB_API}/tools/", HUB_CACHE_FILE, True)
    if not type:
        return workflows
    results = []
    for w in workflows:
        workflow_types = w['versions'][0]['descriptor_type']
        workflow_type = workflow_types[0].lower() if len(workflow_types) > 0 else None
        if workflow_type != type.lower():
            continue
        results.append(w)
    return results

# Get Galaxy workflow from Workflow Hub entry
def get_ga_workflow(w):
    download_url = f"{w['url']}/download"
    ga_workflow = extract_galaxy_workflow_from_zip(download_url)
    return ga_workflow 

# Iterate over Galaxy workflows in the Workflow Hub
def iter_workflows():
    workflows = get_hub_workflows(type="galaxy")
    for wf in workflows:
        ga_w = get_ga_workflow(wf)
        workflow_info = ga_workflow.parse_workflow(ga_w)
        workflow_info.url = wf['url']
        workflow_info.description = wf.get('description', '')
        yield workflow_info

