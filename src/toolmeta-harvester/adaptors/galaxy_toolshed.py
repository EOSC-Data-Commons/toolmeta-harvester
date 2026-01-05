import requests
import json
from pathlib import Path
from lxml import etree
from urllib.parse import urlparse

TOOLShed = "https://toolshed.g2.bx.psu.edu"
CACHE_FILE = "cache/toolshed_registry.json"

def get_json(url):
    r = requests.get(url, timeout=30)
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
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def parse_inputs(tool_xml):
    tree = etree.fromstring(tool_xml.encode())
    inputs = []

    for param in tree.xpath(".//inputs//*"):
        tag = param.tag
        name = param.get("name")
        ptype = param.get("type")
        fmt = param.get("format")

        if name:
            inputs.append({
                "name": name,
                "tag": tag,
                "type": ptype,
                "format": fmt
            })

    return inputs

def load_repositories(use_cache=True):
    if use_cache and is_cached(CACHE_FILE):
        print("Loading registry from cache...")
        return load_json(CACHE_FILE)

    repos = get_json(f"{TOOLShed}/api/repositories")
    save_json(repos, CACHE_FILE)
    return repos

def convert_git_url_to_api(repo_url):
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or parsed.netloc != "github.com":
        return None
    owner, repo = parts[:2]
    repo = repo.removesuffix(".git")
    if len(parts) == 2:
        return f"https://api.github.com/repos/{owner}/{repo}/contents/tools"

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
        # repo_id = repo["id"]
        # owner = repo["owner"]
        # name = repo["name"]
        remote_repository_url = repo["remote_repository_url"]
        if not remote_repository_url:
            continue
        converted_repo_url = convert_git_url_to_api(remote_repository_url)
        if not converted_repo_url:
            continue
        unique_repos.add(converted_repo_url)
    return unique_repos

def crawl_repositories(unique_repos):
    for repo in unique_repos:
        print(f"Crawling repository: {repo}")
        response = requests.get(repo)
        if response.status_code != 200:
            # print(f"Failed to fetch {repo}: {response.status_code}")
            continue
        for entry in response.json():
            if entry['type'] == 'file' and entry['name'].endswith('.xml'):
                xml_url = entry['download_url']
                try:
                    xml = fetch_xml(xml_url)
                    inputs = parse_inputs(xml)
                    print(f"Tool: {entry['name']}, Inputs: {inputs}")
                except Exception as e:
                    # print(f"Failed to parse {xml_url}: {e}")
                    continue
        break

if __name__ == "__main__":
    unique_repos = get_unique_repositories()
    crawl_repositories(unique_repos)

    # print(f"{count}: name: {name}, repo: {remote_repository_url}, converted: {converted_repo_url}")

    # 2. Get installable revisions
#     revisions = get_json(
#         f"{TOOLShed}/api/repositories/{repo_id}/installable_revisions"
#     )
#
#     for rev in revisions:
#         changeset = rev["changeset_revision"]
#
#         # 3. Get metadata for that revision
#         metadata = get_json(
#             f"{TOOLShed}/api/repositories/{repo_id}/metadata/{changeset}"
#         )
#
#         for tool in metadata.get("tools", []):
#             tool_id = tool["id"]
#             tool_xml_path = tool["tool_config"]
#
#             xml_url = f"{TOOLShed}/repos/{owner}/{name}/{tool_xml_path}"
#
#             try:
#                 xml = fetch_xml(xml_url)
#                 inputs = parse_inputs(xml)
#             except Exception:
#                 continue
#
#             registry.append({
#                 "tool_id": tool_id,
#                 "owner": owner,
#                 "repo": name,
#                 "revision": changeset,
#                 "inputs": inputs
#             })
#
# print(f"Collected {len(registry)} tools")
#
