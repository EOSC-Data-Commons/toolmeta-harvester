import logging
import json
import re
import requests
import subprocess
# import requests_cache
from pathlib import Path
from toolmeta_models import ToolGeneric
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from toolmeta_harvester.db.engine import engine

logger = logging.getLogger(__name__)

VIP_INDEX_URL = "https://vip.creatis.insa-lyon.fr/rest/pipelines?public"
BASE_URI = "https://vip.creatis.insa-lyon.fr/rest/pipelines/"
REPO_URL ="https://github.com/virtual-imaging-platform/vip-apps-boutiques-descriptors"
LOCAL_DIR = Path("cache/vip-apps-boutiques-descriptors")


EXT_PATTERN = re.compile(r"\.\w+(?:\.\w+)*")

FILE_TYPES = {
    # --- Core scientific ---
    "mat": ".mat",
    "hdf5": ".h5",
    "hdf": ".hdf",
    "h5": ".h5",
    "netcdf": ".nc",
    "cdf": ".cdf",
    "zarr": ".zarr",
    "root": ".root",

    # --- Tabular / data science ---
    "csv": ".csv",
    "tsv": ".tsv",
    "parquet": ".parquet",
    "feather": ".feather",
    "arrow": ".arrow",
    "json": ".json",
    "xml": ".xml",
    "yaml": ".yaml",
    "yml": ".yaml",

    # --- Statistics / scientific computing ---
    "rds": ".rds",
    "rdata": ".rdata",
    "stata": ".dta",
    "spss": ".sav",
    "pickle": ".pkl",
    "pkl": ".pkl",
    "numpy": ".npy",
    "npz": ".npz",

    # --- Astronomy ---
    "fits": ".fits",
    "fit": ".fits",
    "votable": ".vot",

    # --- Medical imaging ---
    "dicom": ".dcm",
    "dcm": ".dcm",
    "nifti": ".nii",
    "nii": ".nii",
    "nii.gz": ".nii.gz",
    "analyze": ".img",
    "mgh": ".mgh",
    "mgz": ".mgz",

    # --- Bioinformatics / genomics ---
    "fasta": ".fasta",
    "fa": ".fasta",
    "fna": ".fasta",
    "faa": ".fasta",
    "fastq": ".fastq",
    "sam": ".sam",
    "bam": ".bam",
    "cram": ".cram",
    "vcf": ".vcf",
    "bcf": ".bcf",
    "gff": ".gff",
    "gff3": ".gff3",
    "gtf": ".gtf",
    "bed": ".bed",
    "pdb": ".pdb",

    # --- Chemistry / materials ---
    "mol": ".mol",
    "sdf": ".sdf",
    "cml": ".cml",
    "xyz": ".xyz",
    "cif": ".cif",
    "jcamp": ".jdx",
    "jdx": ".jdx",

    # --- Geospatial / earth science ---
    "grib": ".grib",
    "grb": ".grib",
    "bufr": ".bufr",
    "geotiff": ".tiff",
    "tiff": ".tiff",
    "tif": ".tiff",
    "shapefile": ".shp",
    "shp": ".shp",
    "kml": ".kml",
    "kmz": ".kmz",
    "las": ".las",
    "laz": ".laz",
    "dem": ".dem",
    "asc": ".asc",

    # --- Microscopy / imaging ---
    "ome-tiff": ".ome.tiff",
    "ometiff": ".ome.tiff",
    "lsm": ".lsm",
    "czi": ".czi",
    "nd2": ".nd2",
    "mrc": ".mrc",
    "ccp4": ".ccp4",

    # --- Signals / neuroscience ---
    "edf": ".edf",
    "bdf": ".bdf",
    "gdf": ".gdf",
    "tool.b": ".tool.b",
    "xdf": ".xdf",

    # --- Engineering / simulation ---
    "vtk": ".vtk",
    "cgns": ".cgns",
    "exodus": ".exo",
    "exo": ".exo",
    "ensight": ".case",
    "case": ".case",
    "nexus": ".nxs",
    "nxs": ".nxs",

    # --- Generic scientific ---
    "dat": ".dat",
    "txt": ".txt",

    # --- Archives (often used for datasets) ---
    "zip": ".zip",
    "tar": ".tar",
    "tar.gz": ".tar.gz",

    # --- Images (common in scientific contexts) ---
    "png": ".png",
    "jpg": ".jpg",
    "jpeg": ".jpeg",
    "bmp": ".bmp",
    "gif": ".gif",
    "svg": ".svg",
    "pdf": ".pdf",
    "eps": ".eps",
    "ps": ".ps",

    # --- Code / scripts (often shared in scientific projects) ---
    "py": ".py",
    "r": ".r",
    "m": ".m",
    "ipynb": ".ipynb",
    "jl": ".jl",
    "sh": ".sh",
    "bash": ".sh",
    "zsh": ".sh",
    "csh": ".sh",
    "cpp": ".cpp",
    "java": ".java",
    "js": ".js",

}

EXTENSIONS = set(FILE_TYPES.values())

# Initialize requests cache
# requests_cache.install_cache(
#     "cache/vip_cache", backend="sqlite", expire_after=86400
# )

def extract_filetypes(text):
    text_lower = text.lower()
    
    found = set()
    
    # --- (1) explicit extensions ---
    for ext in EXT_PATTERN.findall(text_lower):
        if ext in EXTENSIONS:
            found.add(ext)
    
    # --- (2) word-based lookup ---
    words = re.findall(r"\b[\w\-\.]+\b", text_lower)
    
    for w in words:
        # direct match
        if w in FILE_TYPES:
            found.add(FILE_TYPES[w])
        
        # normalise hyphen variants (e.g. ome-tiff → ometiff)
        w_norm = w.replace("-", "")
        if w_norm in FILE_TYPES:
            found.add(FILE_TYPES[w_norm])

    return sorted(ext.lstrip(".") for ext in found)

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
            slot["file_formats"] = extract_filetypes(input.get("description", ""))
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
