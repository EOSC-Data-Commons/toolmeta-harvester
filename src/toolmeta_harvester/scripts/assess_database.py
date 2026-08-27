from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)


def tool_metadata_to_dict(record: ToolMetadata) -> dict:
    return {
        "title": record.title,
        "description": record.description,
        "raw_description": record.raw_description,
        "version": record.version,
        "license": record.license,
        "identifiers": record.identifiers or [],
        "url": record.url,
        "code_repository": record.code_repository,
        "keywords": record.keywords or [],
        "authors": record.authors or [],
        "types": record.types or [],
        "programming_languages": (record.programming_languages or []),
        "runtime_platforms": (record.runtime_platforms or []),
        "software_requirements": (record.software_requirements or []),
        "software_types": (record.software_types or []),
        "consumes_data": (record.consumes_data or []),
        "produces_data": (record.produces_data or []),
        "date_created": record.date_created,
        "date_published": record.date_published,
        "date_modified": record.date_modified,
    }


def assess_existing_records():
    with Session(engine) as session:
        records = session.query(ToolMetadata).all()

        passed = 0
        failed = 0

        for record in records:
            metadata = tool_metadata_to_dict(record)

            quality = assess_metadata_quality(metadata)

            if quality.passed:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"

            print(f"{status} {record.id} {quality.score:.2f} {record.title!r}")

            if quality.missing:
                print(
                    "  missing:",
                    ", ".join(quality.missing),
                )

            for warning in quality.warnings:
                print(
                    "  warning:",
                    warning,
                )

        print()
        print(f"Total: {len(records)} | Passed: {passed} | Failed: {failed}")


if __name__ == "__main__":
    assess_existing_records()
