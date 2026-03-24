import logging
from toolmeta_harvester.tasks import harvest_vip_tasks as vip
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8080/api/v1/tools/"
TOKEN = ""

def main():
    vip.ensure_repo()
    apps = vip.get_app_metadata()
    logger.info(f"Harvested {len(apps)} VIP apps")
    for (name, version), tool in apps.items():
        logger.debug(f"App: {name}, Version: {version}, Location: {tool['location']}")
        response = vip.post_json_to_registry(tool, API_URL, TOKEN)
        if response.get("success"):
            logger.info(f"Successfully posted {name} version {version} to registry")
        else:
            logger.error(f"Failed to post {name} version {version} to registry: {response.get('error')}")


if __name__ == "__main__":
    main()
