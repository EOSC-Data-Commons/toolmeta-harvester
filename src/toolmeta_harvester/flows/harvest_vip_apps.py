import logging
from pathlib import Path
from toolmeta_harvester import config
from toolmeta_harvester.tasks import harvest_vip_tasks as vip
LOG_FILE = Path("logs/harvest_galaxy_hub_workflows.log")
# Create directory if it does not exist
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE)],
)

logger = logging.getLogger(__name__)

# Important: Ensure ending forward slash in API_URL for correct endpoint construction in post_json_to_registry
# Development API URL
API_URL = "https://tool-registry.eosc-data-commons.dansdemo.nl/api/v1/tools/"
# Production API URL
# API_URL = "https://dev.tools-registry.eosc-data-commons.eu/api/v1/tools/"
TOKEN = config.egi_token()

def harvest_vip():
    vip.ensure_repo()
    apps = vip.get_app_metadata()
    logger.info(f"Harvested {len(apps)} VIP apps")
    for (name, version), tool in apps.items():
        logger.debug(f"App: {name}, Version: {version}, Location: {tool['location']}")
        response = vip.post_json_to_registry(tool, API_URL, TOKEN)
        if response.get("success"):
            logger.info(f"Successfully posted {name} version {version} to registry")
            logger.debug(f"Response: {response}")
        else:
            logger.error(f"Failed to post {name} version {version} to registry: {response.get('error')}")

def patch_uris():
    tools = vip.get_tools(API_URL)
    for tool in tools:
        if tool and tool["archetype"] == "vip_app_boutique":
            uri = tool.get("uri", "")
            uri = uri.replace("\n", "")
            # logger.debug(f"New URI for tool {tool['name']} v{tool['version']}: {uri}")
            patch_data = {"uri": uri,
                          "location": uri}
            response = vip.patch_tool(tool["id"], patch_data, API_URL, TOKEN)
            if response.get("success"):
                logger.info(f"Successfully patched {tool['id']}")
                logger.debug(f"Response: {response}")
            else:
                logger.error(f"Failed to patch {tool['id']}: {response.get('error')}")

if __name__ == "__main__":
    # patch_uris()
    harvest_vip()
