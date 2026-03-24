import logging
import requests
from toolmeta_harvester import config

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Important: Ensure ending forward slash in API_URL for correct endpoint construction in post_json_to_registry
API_URL = "https://dev.tools-registry.eosc-data-commons.eu/api/v1/tools/"
# Get your token from egi https://aai.egi.eu/token/ and set it in the config file or environment variable as needed
TOKEN = config.egi_token()


def get_tool_metadata():
    results = []
    # Get the tool descriptions from the source provider (e.g., VIP index, local JSON files, etc.)
    # TODO: Implement the logic to fetch and process tool metadata from the source providera

    tool_descriptions = []  # Replace with actual fetching logic

    # Process each tool description and construct the tool metadata dictionary
    for data in tool_descriptions:
        tool = {
            "uri": data.get("uri", ""),
            "name": data.get("name", ""),
            "version": data.get("version", ""),
            "location": data.get("location", ""),
            "archetype": "your_archetype_here",  # Replace with the appropriate archetype
            "description": data.get("description", ""), # Replace with actual field name for description if different
            "input_file_formats": data.get("input_file_formats", []), # Replace with actual field name for input file formats if different
            "output_file_formats": data.get("output_file_formats", []), # Replace with actual field name for output file formats if different
            "input_file_descriptions": data.get("input_file_descriptions", []), # Replace with actual field name for input file descriptions if different
            "output_file_descriptions": data.get("output_file_descriptions", []), # Replace with actual field name for output file descriptions if different
            "raw_metadata": data, # Store the original metadata for reference
            "metadata_version": data.get("schema-version", ""), # Replace with the actual field name for metadata version if different
            "metadata_schema": {}, # Replace with actual schema if available
            "metadata_type": "your_metadata_type_here",  # Replace with the appropriate metadata type

        }
        results.append(tool)
    return results

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

def main():
    # Step 1: Fetch and process tool metadata from the source provider
    logger.info("Fetching tool metadata from source provider...")
    tools = get_tool_metadata()

    # Step 2: Post each tool metadata to the registry
    logger.info(f"Posting {len(tools)} tools to the registry...")
    for tool in tools:
        response = post_json_to_registry(tool, API_URL, TOKEN)
        if response.get("success"):
            logger.info(f"Successfully posted {tool['name']} version {tool['version']} to registry")
            logger.debug(f"Response: {response}")
        else:
            logger.error(f"Failed to post {tool['name']} version {tool['version']} to registry: {response.get('error')}")

if __name__ == "__main__":
    main()
