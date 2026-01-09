from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import Base, Repository, Tool, ToolInput, ToolOutput
from toolmeta_harvester.adaptors import galaxy_toolshed
from requests.exceptions import HTTPError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

def create_tables():
    """Create all tables in the database."""
    Base.metadata.create_all(engine)

def populate_repositories():
    """Populate the repository table with initial data."""
    galaxy_repos = galaxy_toolshed.get_unique_repositories()
    with Session(engine) as session:
        session.add_all(Repository(url=u, status="pending", source_type="galaxy") 
            for u in galaxy_repos)
        session.commit()

def process_pending_repositories():
    """Process repositories with pending status."""
    with Session(engine) as session:
        pending_repos = session.query(Repository).filter_by(status="pending").all()
        # pending_repos = session.query(Repository).filter_by(status="processed").all()
        for repo in pending_repos:
            try:
                tools = galaxy_toolshed.crawl_repository(repo.url)
                print(f"Processing repository: {repo.url} with {len(tools)} tools found.")
                for tool in tools:
                    try:
                        db_tool = Tool(
                            # id=tool.id,
                            name=tool.id,
                            version=tool.version,
                            command=tool.command.encode('utf-8') if tool.command else None,
                            source_type="galaxy",
                            source_url=tool.repo_url,
                            raw=tool.raw.encode('utf-8'),
                            raw_format=tool.raw_format
                        )
                        session.add(db_tool)
                        session.flush()  # Ensure db_tool.id is populated

                        print(f"Tool inputs: {tool.inputs}")

                        for input in tool.inputs:
                            print(f"Processing input: {input}")
                            db_input = ToolInput(
                                tool_id=db_tool.id,
                                name=input['name'],
                                type=input['type'],
                                format=[],
                                label=input.get('label')
                            )
                            formats = input.get('format').split(',') if input.get('format') else []
                            for fmt in formats:
                                db_input.format.append(fmt.strip())

                            session.add(db_input)
                            session.flush()

                        for output in tool.outputs:
                            db_output = ToolOutput(
                                tool_id=db_tool.id,
                                name=output['name'],
                                type=output['type'],
                                format=[],
                                label=output.get('label')
                            )
                            formats = output.get('format').split(',') if output.get('format') else []
                            for fmt in formats:
                                db_output.format.append(fmt.strip())

                            session.add(db_output)
                            session.flush()
                    except IntegrityError as e:
                        print(f"IntegrityError for tool {tool.id}: {e}")
                        session.rollback()

                repo.status = "processed"
                repo.no_tools = len(tools)
            except HTTPError as e:
                if e.response.status_code == 403:
                    print(f"Access forbidden (403) to repository: {repo.url}")
                    break
                else:
                    print(f"HTTPError {e.response.status_code} for repository {repo.url}")
                    repo.status = "error"
                    repo.eror_code = str(e.response.status_code)
        session.commit()
        session.flush()

if __name__ == "__main__":
    create_tables()
    print("All tables created successfully.")
    populate_repositories()
    print("Repository table populated successfully.")
    process_pending_repositories()
    print("Pending repositories processed successfully.")

