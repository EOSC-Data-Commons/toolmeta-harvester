import requests
import requests_cache
import json
import yaml
from urllib.parse import urljoin
from dataclasses import dataclass
from pathlib import Path
from lxml import etree
from lxml.etree import XMLSyntaxError
from urllib.parse import urlparse
from toolmeta_harvester.config import load_git_config

TOOLShed = "https://toolshed.g2.bx.psu.edu"
CACHE_FILE = "cache/toolshed_registry.json"

galaxy_shed_ignore_list = ["kubernetes"]

GIT_CONFIG = load_git_config()
GITHUB_TOKEN = GIT_CONFIG.api_key

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Initialize requests cache 
requests_cache.install_cache('toolshed_cache', 
                             backend='sqlite',
                             expire_after=86400)

@dataclass(frozen=True)
class ToolInfo:
    id: str
    tool_name: str
    owner: str
    version: str
    description: str
    categories: list
    inputs: list
    outputs: list
    repo_url: str
    tool_type: str = "galaxy_tool"

def get_json(url):
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

def is_cached(filename):
    return Path(filename).is_file()

def fetch_xml(url):
    # r = requests.get(url, timeout=30, headers=HEADERS)
    # r.raise_for_status()
    # return r.text
    return fetch_text_file(url)

def fetch_text_file(url):
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    return r.text

def get_macro_files(tree):
    return [macros.text.strip() for macros in tree.xpath("//macros/import")]

def extract_tokens(tree):
    tokens = {}
    for token in tree.xpath("//token"):
        name = token.get("name")
        value = token.text
        tokens[name] = value
    return tokens

def substitute_tokens(xml_str, tokens):
    for k, v in tokens.items():
        # if "VERSION" in k or "PREFIX" in k:
        xml_str = xml_str.replace(k, v)
    return xml_str

def parse_xml(tool_xml, dir_contents=None, repo_url=""):
    try:
        tree = etree.fromstring(tool_xml.encode())
    except XMLSyntaxError as e:
        return None

    if tree.tag != "tool":
        return None
    macro_files = get_macro_files(tree)
    new_xml = tool_xml
    tokens = {}
    for macro_file in macro_files:
        # print("Processing macro file:", macro_file)
        macro_url = get_file_url(dir_contents or [], macro_file)
        if not macro_url:
            continue
        macro_xml = fetch_xml(macro_url)
        try:
            macro_tree = etree.fromstring(macro_xml.encode())
        except XMLSyntaxError as e:
            # print(f"Error fetching macro file {macro_file} from {macro_url}: {e}")
            # Some macro.xml files use relative paths
            if macro_xml.startswith("../"):
                macro_url = urljoin(macro_url, macro_xml)
                print(macro_url)
                macro_xml = fetch_xml(macro_url)
                macro_tree = etree.fromstring(macro_xml.encode())
        tokens.update(extract_tokens(macro_tree))

    # Tokens can be defined in the main tool XML as well
    tokens.update(extract_tokens(tree))
    # Substitute tokens until no changes
    tmp_xml = None
    while tmp_xml != new_xml: 
        tmp_xml = new_xml
        new_xml = substitute_tokens(new_xml, tokens)


    try:
        tree = etree.fromstring(new_xml.encode())
    except Exception as e:
        print("Error parsing XML after token substitution:", e)
        print(new_xml)
    inputs = []
    outputs = []
    for param in tree.xpath(".//inputs//*"):
        
        tag = param.tag
        if tag.lower() != "param":
            continue
        name = param.get("name")
        ptype = param.get("type")
        if ptype == "select":
            continue
        fmt = param.get("format")
        label = param.get("label")

        inputs.append({
            "name": name,
            "tag": tag,
            "type": ptype,
            "format": fmt,
            "label": label
        })
    for param in tree.xpath(".//outputs//*"):
        tag = param.tag
        if tag.lower() != "data":
            continue
        name = param.get("name")
        ptype = "data"
        fmt = param.get("format")
        label = param.get("label")

        outputs.append({
            "name": name,
            "tag": tag,
            "type": ptype,
            "format": fmt,
            "label": label
        })

    tool_name = tree.get("name")
    tool_id = tree.get("id")
    version = tree.get("version")
    # command = tree.findtext("command")
    shed_yml = get_shed_yml(repo_url)
    description = tree.findtext("description") or shed_yml.get('long_description') or shed_yml.get('description') or ''
    owner = shed_yml.get('owner', '')
    categories = shed_yml.get('categories', [])
    categories = [c.strip().lower() for c in categories if c.strip()]

    return ToolInfo(
        id=tool_id,
        tool_name=tool_name,
        version=version,
        description=description,
        owner=owner,
        categories=categories,
        inputs=inputs,
        outputs=outputs,
        repo_url=repo_url,
    )

def load_repositories(use_cache=True):
    if use_cache and is_cached(CACHE_FILE):
        print("Loading registry from cache...")
        return load_json(CACHE_FILE)

    repos = get_json(f"{TOOLShed}/api/repositories")
    save_json(repos, CACHE_FILE)
    return repos

# def convert_git_url_to_api(repo_url):
#     parsed = urlparse(repo_url)
#     parts = parsed.path.strip("/").split("/")
#     if len(parts) < 2 or parsed.netloc != "github.com":
#         return None
#     owner, repo = parts[:2]
#     repo = repo.removesuffix(".git")
#     if len(parts) == 2:
#         return f"https://api.github.com/repos/{owner}/{repo}/contents/tools"
#         # return f"https://api.github.com/repos/{owner}/{repo}/contents"
#
#     kind = parts[2]
#     if kind not in {"tree", "blobl"}:
#         return None
#     branch = parts[3]
#     path = "/".join(parts[4:]) if len(parts) > 4 else ""
#
#     if branch == "master" or branch == "main":
#         return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
#     
#     return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"

def convert_git_url_to_api(repo_url):
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or parsed.netloc != "github.com":
        return None
    owner, repo = parts[:2]
    repo = repo.removesuffix(".git")
    if len(parts) == 2:
        # return f"https://api.github.com/repos/{owner}/{repo}/contents/tools"
        return f"https://api.github.com/repos/{owner}/{repo}/contents"

    kind = parts[2]
    if kind not in {"tree", "blobl"}:
        return None
    branch = parts[3]
    path = "/".join(parts[4:]) if len(parts) > 4 else ""

    if branch == "master" or branch == "main":
        return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"

def get_unique_repositories():
    repos = load_repositories(use_cache=True)
    unique_repos = set()
    for repo in repos:
        if repo["name"].lower() in galaxy_shed_ignore_list:
            continue
        remote_repository_url = repo["remote_repository_url"]
        if not remote_repository_url:
            continue
        converted_repo_url = convert_git_url_to_api(remote_repository_url)
        if not converted_repo_url:
            continue
        unique_repos.add(converted_repo_url)
    return unique_repos

def get_file_url(contents, file_name):
    for entry in contents:
        if 'type' not in entry or 'name' not in entry:
            continue
        if entry['type'] == 'file' and entry['name'] == file_name:
            return entry['download_url']
    return None

def has_shed_yml(contents):
    for entry in contents:
        if 'type' not in entry or 'name' not in entry:
            continue
        if entry['type'] == 'file' and entry['name'].lower() == '.shed.yml':
            return True
    return False

def get_shed_yml(git_url):
    contents = get_json(git_url)
    for entry in contents:
        if 'type' not in entry or 'name' not in entry:
            continue
        if entry['type'] == 'file' and entry['name'].lower() == '.shed.yml':
            file_contents = fetch_text_file(entry['download_url'])
            data = yaml.safe_load(file_contents)
            return data
    return False

def get_git_tree(repo_api_url):
    parsed = urlparse(repo_api_url)
    parts = parsed.path.strip("/").split("/")
    owner = parts[1]
    repo = parts[2]
    r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
        headers=HEADERS,
    )
    r.raise_for_status()

    branch = r.json()["default_branch"]
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
    r = requests.get(tree_url, params={"recursive": "1"}, timeout=30, headers=HEADERS)
    r.raise_for_status()
    return (branch, r.json())

def strip_query(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def get_tool_folders(repo_api_url):
    branch, file_tree = get_git_tree(repo_api_url)
    file_list = file_tree.get("tree", [])
    tool_folders = set()
    for item in file_list:
        if item["type"] == "blob" and item["path"].lower().endswith(".shed.yml"):
            folder = "/".join(item["path"].split("/")[:-1])
            folder = f"{strip_query(repo_api_url)}/{folder}?ref={branch}"
            # print("Found tool folder:", folder)
            tool_folders.add(folder)
    return list(tool_folders)

def smart_crawl_repository(repo_api_url):
    tool_folders = get_tool_folders(repo_api_url)
    collector = []
    for url in tool_folders:
        # print("Crawling tool folder:", url)
        tools = crawl_repository(url)
        print(f"Found {len(tools)} tools in {url}")
        collector.extend(tools)
    return collector

def smart_crawl_repository_iter(repo_api_url):
    tool_folders = get_tool_folders(repo_api_url)
    for url in tool_folders:
        # print("Crawling tool folder:", url)
        tools = crawl_repository(url)
        print(f"Found {len(tools)} tools in {url}")
        yield (url, tools)

def crawl_repository(repo, collector=None):
    if collector is None:
        collector = []
    if "depricated" in repo.lower():
        return collector
    print(f"Crawling repository: {repo}")
    response = requests.get(repo, timeout=30, headers=HEADERS)
    # print(f"Response status code: {response.status_code} for {repo}")
    # print(response.text)
    response.raise_for_status()
    # if response.status_code == 403:
    #     print(f"Rate limited when accessing {repo}")
    #     sleep(3610) # rate limit for unauthenticated requests 60 requests per 1 hour and 5000 per hour for authenticated
    #     crawl_repository(repo, collector)
    #     raise Htt
    #     return collector
    # if response.status_code != 200:
    #     print(f"Failed to fetch {repo}: {response.status_code}")
    #     return collector
    has_shed_file = has_shed_yml(response.json())
    for entry in response.json():
        if 'type' not in entry or 'name' not in entry:
            continue
        if entry['type'] == 'file' and entry['name'].lower().endswith('.xml') and has_shed_file:
            xml_url = entry['download_url']
            # try:
            xml = fetch_xml(xml_url)
            tool = parse_xml(xml, response.json(), repo)
            
            if not tool:
                # print(f"Skipping non-tool XML: {xml_url}")
                continue
            collector.append(tool)
            # print(f"Tool: {tool.id}, Version: {tool.version}, Inputs: {tool.inputs}, Outputs: {tool.outputs}, Command: {tool.command}")
            # print(f"Tool: {tool.id}, Version: {tool.version}")
            # except Exception as e:
            #     print(f"Error processing {xml_url}: {e}")
            #     continue
        if entry["type"] == "dir" and not has_shed_file:
            dir_url = entry["url"]
            crawl_repository(dir_url, collector)
    return collector

