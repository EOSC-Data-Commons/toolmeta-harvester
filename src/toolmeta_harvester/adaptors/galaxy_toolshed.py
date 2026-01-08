import requests
import json
from dataclasses import dataclass
from pathlib import Path
from lxml import etree
from urllib.parse import urlparse

TOOLShed = "https://toolshed.g2.bx.psu.edu"
CACHE_FILE = "cache/toolshed_registry.json"

@dataclass(frozen=True)
class ToolInfo:
    id: str
    tool_name: str
    version: str
    inputs: list
    outputs: list
    command: str

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
        xml_str = xml_str.replace(k, v)
    return xml_str

# def collect_macros(tree):
#     macros = {}
#     for xml_macro in tree.xpath("//xml[@name]"):
#         macros[xml_macro.get("name")] = list(xml_macro)
#     return macros
#
# def expand_macros(tree, macros):
#     for expand in tree.xpath("//expand[@macro]"):
#         name = expand.get("macro")
#
#         if name not in macros:
#             continue
#
#         parent = expand.getparent()
#         index = parent.index(expand)
#
#         for node in macros[name]:
#             parent.insert(index, etree.fromstring(etree.tostring(node)))
#             index += 1
#
#         parent.remove(expand)

def parse_xml(tool_xml, dir_contents=None):
    tree = etree.fromstring(tool_xml.encode())
    macro_files = get_macro_files(tree)
    new_xml = tool_xml
    for macro_file in macro_files:
        macro_url = get_file_url(dir_contents or [], macro_file)
        if not macro_url:
            continue
        macro_xml = fetch_xml(macro_url)
        macro_tree = etree.fromstring(macro_xml.encode())
        tokens = extract_tokens(macro_tree)
        new_xml = substitute_tokens(new_xml, tokens)
    tree = etree.fromstring(new_xml.encode())
    inputs = []
    outputs = []

    if tree.tag != "tool":
        return (None, None, None)

    for param in tree.xpath(".//inputs//*"):
        tag = param.tag
        name = param.get("name")
        ptype = param.get("type")
        fmt = param.get("format")
        label = param.get("label")

        if name:
            inputs.append({
                "name": name,
                "tag": tag,
                "type": ptype,
                "format": fmt,
                "label": label
            })
    for param in tree.xpath(".//outputs//*"):
        tag = param.tag
        name = param.get("name")
        ptype = param.get("type")
        fmt = param.get("format")
        label = param.get("label")

        if name:
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
    command = tree.findtext("command")

    return ToolInfo(
        id=tool_id,
        tool_name=tool_name,
        version=version,
        inputs=inputs,
        outputs=outputs,
        command=command
    )

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

def get_file_url(contents, file_name):
    for entry in contents:
        if entry['type'] == 'file' and entry['name'] == file_name:
            return entry['download_url']
    return None

def has_shed_yml(contents):
    for entry in contents:
        if entry['type'] == 'file' and entry['name'] == '.shed.yml':
            return True
    return False


# def crawl_repositories(unique_repos):
#     for repo in unique_repos:
#         print(f"Crawling repository: {repo}")
#         response = requests.get(repo)
#         if response.status_code != 200:
#             print(f"Failed to fetch {repo}: {response.status_code}")
#             continue
#         has_shed_file = has_shed_yml(response.json())
#         for entry in response.json():
#             if entry['type'] == 'file' and entry['name'].endswith('.xml') and has_shed_file:
#                 xml_url = entry['download_url']
#                 try:
#                     xml = fetch_xml(xml_url)
#                     
#                     # inputs = parse_inputs(xml)
#                     tool = parse_xml(xml, response.json())
#                     if not tool.id:
#                         print(f"Skipping non-tool XML: {xml_url}")
#                         continue
#                     # print(f"Tool: {entry['name']}, Inputs: {inputs}")
#                     print(f"Tool: {tool.id}, Version: {tool.version}, Inputs: {tool.inputs}, Outputs: {tool.outputs}, Command: {tool.command}")
#                 except Exception as e:
#                     print(f"Failed to parse {xml_url}: {e}")
#                     continue
#             if entry["type"] == "dir" and not has_shed_file:
#                 dir_url = entry["url"]
#                 print("Recursing into directory:", dir_url)
#                 crawl_repositories({dir_url})

def crawl_repository(repo, collector=[]):
    response = requests.get(repo)
    if response.status_code != 200:
        # print(f"Failed to fetch {repo}: {response.status_code}")
        return []
    has_shed_file = has_shed_yml(response.json())
    for entry in response.json():
        if entry['type'] == 'file' and entry['name'].endswith('.xml') and has_shed_file:
            xml_url = entry['download_url']
            try:
                xml = fetch_xml(xml_url)
                
                # inputs = parse_inputs(xml)
                tool = parse_xml(xml, response.json())
                if not tool.id:
                    print(f"Skipping non-tool XML: {xml_url}")
                    continue
                collector.append(tool)
                # print(f"Tool: {entry['name']}, Inputs: {inputs}")
                # print(f"Tool: {tool.id}, Version: {tool.version}, Inputs: {tool.inputs}, Outputs: {tool.outputs}, Command: {tool.command}")
            except Exception as e:
                # print(f"Failed to parse {xml_url}: {e}")
                continue
        if entry["type"] == "dir" and not has_shed_file:
            dir_url = entry["url"]
            print("Recursing into directory:", dir_url)
            crawl_repository(dir_url, collector)
    return collector

if __name__ == "__main__":
    unique_repos = get_unique_repositories()

    for repo in unique_repos:

        tools = crawl_repository(repo)
        for tool in tools:
            print(f"Tool: {tool.id}, Version: {tool.version}, Inputs: {tool.inputs}, Outputs: {tool.outputs}, Command: {tool.command}")


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
