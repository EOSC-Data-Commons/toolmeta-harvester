import logging
from pathlib import Path
from toolmeta_harvester import config
from toolmeta_harvester.tasks import harvest_vip_tasks as vip
LOG_FILE = Path("logs/harvest_vip_workflows.log")
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
# Testing API URL
# API_URL = "http://tool-registry.eosc-data-commons.dansdemo.nl/api/v1/tools/"

# Warehouse dev API URL
# API_URL = "https://dev.tools-registry.eosc-data-commons.eu/api/v1/tools/"

# Production API URL
API_URL = "https://tools-registry.eosc-data-commons.eu/api/v1/tools/"

TOKEN = config.egi_token()

def harvest_vip_using_postgres_backend():
    session = vip.get_db_session()
    vip.ensure_repo()
    apps = vip.get_app_metadata()
    logger.info(f"Harvested {len(apps)} VIP apps")
    counter = 0
    for (name, version), tool in apps.items():
        (tool_from_db, flag) = vip.add_json_to_db(tool, session)
        if not tool_from_db:
            logger.error(f"Failed to add {name} version {version} to database")
            continue
        if flag==1:
            logger.info(f"App: {name}, Version: {version}, URI: {tool['uri']}")
            logger.debug(f"Input slots: {tool.get('input_slots', [])}")
            logger.info(f"Successfully added {name} id {tool_from_db.id} to database")
            counter += 1

    if counter == 0:
        logger.info("No new VIP apps were added to the database")
    else:
        logger.info(f"Successfully added {counter} VIP apps to the database")

def harvest_vip_using_tool_registry_rest_api():
    registered_apps = vip.get_vip_tools_from_registry(API_URL)
    app_uris = [app['uri'] for app in registered_apps]
    vip.ensure_repo()
    apps = vip.get_app_metadata()
    logger.info(f"Harvested {len(apps)} VIP apps")
    counter = 0
    for (name, version), tool in apps.items():
        if tool['uri'] in app_uris:
            logger.info(f"App: {name}, Version: {version} already registered, skipping")
            continue
        logger.debug(f"App: {name}, Version: {version}, Location: {tool['location']}")
        response = vip.post_json_to_registry(tool, API_URL, TOKEN)
        if response.get("success"):
            tool_id = response.get("response", {}).get("tool_id")
            logger.info(f"Successfully posted {name} version {version} to registry with id {tool_id}")
            logger.debug(f"Response: {response}")
            counter += 1
        else:
            logger.error(f"Failed to post {name} version {version} to registry: {response.get('error')}")
    if counter == 0:
        logger.info("No new VIP apps were posted to the registry")
    else:
        logger.info(f"Successfully posted {counter} VIP apps to the registry")


if __name__ == "__main__":
    # Choose method to register the tools either:
    # - Using the Postgres backend (uncomment the line below)
    # harvest_vip_using_postgres_backend()
    # - Using the Tool Registry REST API (uncomment the line below)
    harvest_vip_using_tool_registry_rest_api()
