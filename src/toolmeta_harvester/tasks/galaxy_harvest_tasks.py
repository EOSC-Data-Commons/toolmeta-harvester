import logging
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    ArtifactHarvest,
    ShedTool,
    ShedToolInput,
    ShedToolOutput,
    GalaxyWorkflowArtifact,
)
from toolmeta_harvester.adaptors import galaxy_toolshed
from requests.exceptions import HTTPError
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def create_tables():
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def populate_harvests_table_with_shed_tools():
    """Populate the repository table with initial data."""
    galaxy_repos = galaxy_toolshed.get_unique_repositories()
    with Session(engine) as session:
        session.add_all(
            ArtifactHarvest(
                url=u,
                status="pending",
                artifact_type="galaxy_shed_tool",
                source_type="toolshed.g2.bx.psu.edu",
            )
            for u in galaxy_repos
        )
        session.commit()


def get_tools_from_db():
    """Retrieve all tools from the database."""
    with Session(engine) as session:
        tools = session.query(ShedTool.id, ShedTool.name, ShedTool.version).all()
        return tools


def get_error_repositories():
    """Process repositories with error status."""
    with Session(engine) as session:
        error_repos = (
            session.query(ArtifactHarvest)
            .filter_by(status="error")
            .filter_by(artifact_type="galaxy_shed_tool")
            .all()
        )
        return [r.url for r in error_repos]


def get_all_repositories():
    """Process repositories with error status."""
    with Session(engine) as session:
        error_repos = (
            session.query(ArtifactHarvest)
            .filter_by(artifact_type="galaxy_shed_tool")
            .all()
        )
        for repo in error_repos:
            logger.debug(f"Repository: {repo.url} with status: {repo.status}")


def process_single_repository(repo_url, session):
    # tools = galaxy_toolshed.smart_crawl_repository(repo_url)
    # print(f"Processing repository: {repo_url} with {len(tools)} tools found.")
    tool_folders = galaxy_toolshed.get_tool_folders(repo_url)
    for url in tool_folders:
        results = session.query(ArtifactHarvest).filter_by(url=url).all()
        repo = None
        if len(results) > 0:
            repo = results[0]
            if repo.status == "completed":
                logger.debug(
                    f"Repository {url} already exists in the database. Skipping."
                )
                continue
        else:
            repo = ArtifactHarvest(
                url=url, status="pending", artifact_type="galaxy_shed_tool"
            )
            session.add(repo)
            session.commit()
            session.flush()
        try:
            tools = galaxy_toolshed.crawl_repository(url)

            for tool in tools:
                add_tool_to_db(tool, session)
                repo.status = "processed"
                session.commit()
                session.flush()

        except Exception as e:
            logger.error(f"Error processing repository {url}: {e}")
            repo.status = "error"
            session.commit()
            session.flush()
            continue


def get_db_session():
    return Session(engine)


def add_workflow_to_db(wf, session):
    if not session:
        session = Session(engine)
    try:
        db_wf = GalaxyWorkflowArtifact(
            id=wf.uuid,
            name=wf.name,
            version=wf.version,
            description=wf.description,
            url=wf.url,
            input_toolshed_tools=[t.uri for t in wf.input_tools],
            output_toolshed_tools=[t.uri for t in wf.output_tools],
            toolshed_tools=wf.toolshed_tools,
            raw_ga=wf.raw_ga,
            tags=wf.tags,
        )
        session.add(db_wf)
        session.flush()  # Ensure db_tool.id is populated
        logger.info(
            f"Adding workflow: {db_wf.id}, {db_wf.name}, version: {db_wf.version}"
        )

        session.commit()
        session.flush()
    except IntegrityError as e:
        logger.error(f"IntegrityError for workflow tool {db_wf.id}: {e}")
        session.rollback()


def add_tool_to_db(tool, session):
    if not session:
        session = Session(engine)
    try:
        db_tool = ShedTool(
            uri=tool.uri,
            id=tool.id,
            name=tool.tool_name,
            version=tool.version,
            description=tool.description,
            owner=tool.owner,
            categories=tool.categories,
            source_type="shed.g2.bx.psu.edu",
            source_url=tool.repo_url,
        )
        session.add(db_tool)
        # session.commit()
        session.flush()  # Ensure db_tool.id is populated
        logger.info(
            f"Adding tool: {db_tool.id}, {db_tool.name}, version: {db_tool.version}"
        )

        for input in tool.inputs:
            logger.debug(f"Processing input: {input}")
            db_input = ShedToolInput(
                tool_uri=db_tool.uri,
                name=input["name"],
                type=input["type"],
                format=[],
                label=input.get("label"),
            )
            formats = input.get("format").split(",") if input.get("format") else []
            for fmt in formats:
                db_input.format.append(fmt.strip())

            session.add(db_input)
            # session.commit()
            # session.flush()

        for output in tool.outputs:
            db_output = ShedToolOutput(
                tool_uri=db_tool.uri,
                name=output["name"],
                type=output["type"],
                format=[],
                label=output.get("label"),
            )
            formats = output.get("format").split(",") if output.get("format") else []
            for fmt in formats:
                db_output.format.append(fmt.strip())

            session.add(db_output)

        session.commit()
        session.flush()
    except IntegrityError as e:
        logger.error(f"IntegrityError for tool {tool.id}: {e}")
        session.rollback()


def process_pending_repositories():
    """Process repositories with pending status."""
    with Session(engine) as session:
        pending_repos = session.query(ArtifactHarvest).filter_by(status="pending").all()
        for repo in pending_repos:
            try:
                tools = galaxy_toolshed.smart_crawl_repository(repo.url)
                logger.info(
                    f"Processing repository: {repo.url} with {len(tools)} tools found."
                )
                for tool in tools:
                    add_tool_to_db(tool, session)
                repo.status = "processed"
                repo.no_tools = len(tools)
                session.commit()
                session.flush()
            except HTTPError as e:
                if e.response.status_code == 403:
                    logger.error(f"Access forbidden (403) to repository: {repo.url}")
                    session.commit()
                    session.flush()
                    raise e
                else:
                    logger.error(
                        f"HTTPError {e.response.status_code} for repository {repo.url}"
                    )
                    repo.status = "error"
                    repo.eror_code = str(e.response.status_code)
                    session.commit()
                    session.flush()
            except Exception as e:
                logger.error(f"Error processing repository {repo.url}: {e}")
                repo.status = "error"
                session.commit()
                session.flush()

        session.commit()
        session.flush()


def name_variants(name):
    variants = set()
    variants.add(name)
    variants.add(name.replace("-", "_"))
    variants.add(name.replace("_", "-"))
    variants.add(name.replace("_", ""))
    variants.add(name.replace("-", ""))
    variants.add(name.split("_")[0])
    variants.add(name.split("-")[0])
    return variants


def get_tools_not_in_db():
    repos = galaxy_toolshed.load_repositories()
    tools_in_db = get_tools_from_db()
    tool_names_in_db = [t[1].lower() for t in tools_in_db]
    tools_in_repos = [t["name"].lower() for t in repos]
    tool_index = {}
    for r in repos:
        tool_index[r["name"]] = r
    # print(tool_names_in_db)a
    cnt = 0
    for tool in tools_in_repos:
        found = False
        for variant in name_variants(tool):
            if variant in tool_names_in_db:
                found = True
                break
        if not found:
            t = tool_index[tool]
            url = t["remote_repository_url"]
            if not url:
                continue
            if "github.com" not in url:
                continue
            cnt += 1
            logger.debug(f"{t['name']}, {t['remote_repository_url']}")

    logger.debug(f"Total tools not in DB: {cnt}")


# def compare_converters():
#     """Compare tools in the database with those in the Galaxy Tool Shed."""
#     repos = galaxy_toolshed.load_repositories()
#     error_repos = get_error_repositories()
#     results = []
#     for repo in repos:
#         url = repo["remote_repository_url"]
#         if not url:
#             continue
#         r1 = galaxy_toolshed.convert_git_url_to_api(repo["remote_repository_url"])
#         if r1 not in error_repos:
#             continue
#         r2 = galaxy_toolshed.convert_git_url_to_api2(repo["remote_repository_url"])
#         if r1 != r2:
#             results.append((repo["name"], r1, r2))
#
#     return results
#

# def get_tools_with_incorrect_version():
#     with Session(engine) as session:
#         stmt = select(ShedTool).where(ShedTool.version.contains("VERSION"))
#         tools = session.execute(stmt).scalars().all()
#         return tools


# def galaxy_process_errors_flow():
#     fixed_url = compare_converters()
#     for name, old_url, new_url in fixed_url:
#         with Session(engine) as session:
#             repo = session.query(GalaxyWorkflowArtifact).filter_by(url=old_url).first()
#             if repo:
#                 logger.debug(f"Updating repository URL from {old_url} to {new_url}")
#                 repo.url = new_url
#                 repo.status = "pending"
#                 repo.eror_code = None
#
#                 session.commit()
#                 session.flush()
#
#     try:
#         process_pending_repositories()
#         logger.info("Pending repositories processed successfully.")
#     except Exception as e:
#         logger.error(f"Error processing pending repositories: {e}")
#
#
# def galaxy_fix_version_flow():
#     with Session(engine) as session:
#         stmt = select(Tool).where(Tool.version.contains("VERSION"))
#         tools = session.execute(stmt).scalars().all()
#         for tool in tools:
#             try:
#                 repo_url = tool.source_url
#                 tools_fetched = galaxy_toolshed.crawl_repository(repo_url)
#                 for t in tools_fetched:
#                     if t.id == tool.name:
#                         tool.version = t.version
#                         session.commit()
#                         session.flush()
#                         print(f"Updated tool {tool.name} to version {tool.version}")
#                         break
#             except Exception as e:
#                 print(f"Error fixing tool {tool.id}: {e}")
#
#
# def galaxy_main_process_flow():
#     create_tables()
#     print("All tables created successfully.")
#     populate_repositories()
#     print("Repository table populated successfully.")
#
#     try:
#         process_pending_repositories()
#         print("Pending repositories processed successfully.")
#     except Exception as e:
#         print(f"Error processing pending repositories: {e}")
#
#
# def galaxy_single_repo_crawl_flow(repo_url):
#     create_tables()
#     print("All tables created successfully.")
#     with Session(engine) as session:
#         process_single_repository(repo_url, session)
#         print("Single repository processed successfully.")
#
#
# def galaxy_test_flow():
#     test_url = "https://api.github.com/repos/WhoisDonlee/tools-iuc/contents"
#     # test_url=" https://api.github.com/repos/WhoisDonlee/tools-iuc/contents/tools/checkm?ref=main"
#     tools = galaxy_toolshed.smart_crawl_repository(test_url)
#     # tools = galaxy_toolshed.crawl_repository(test_url)
#     for tool in tools:
#         print(f"Found tool: {tool.id}, version: {tool.version}")
#
#
# def galaxy_update_description_flow():
#     with Session(engine) as session:
#         tools = session.query(Tool).all()
#         for tool in tools:
#             if tool.description or tool.owner:
#                 continue
#             try:
#                 repo_url = tool.source_url
#                 data = galaxy_toolshed.get_shed_yml(repo_url)
#                 description = data.get("long_description", "")
#                 short_description = data.get("description", "")
#                 if not description:
#                     description = short_description
#                 owner = data.get("owner", "")
#                 categories = data.get("categories", [])
#                 categories = [c.strip().lower() for c in categories if c.strip()]
#                 tool.description = description
#                 tool.owner = owner
#                 tool.categories = categories
#                 session.commit()
#                 session.flush()
#                 print(
#                     f"Updating tool {tool.name} owner: {owner}, categories: {
#                         categories
#                     }"
#                 )
#             except Exception as e:
#                 print(
#                     f"Error updating description for tool {tool.id}, {tool.name}, {
#                         tool.source_url
#                     }: {e}"
#                 )
#                 continue
#
#
# if __name__ == "__main__":
#     # galaxy_update_description_flow()
#     # print("Tool descriptions updated successfully.")
#     repo_url = "https://api.github.com/repos/WhoisDonlee/tools-iuc/contents"
#     galaxy_single_repo_crawl_flow(repo_url)
#     # galaxy_test_flow()
#     # galaxy_main_process_flow()
#     # galaxy_fix_version_flow()
#     # galaxy_process_errors_flow()
