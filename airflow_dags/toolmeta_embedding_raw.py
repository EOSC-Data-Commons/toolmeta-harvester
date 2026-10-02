import hashlib
import os
import uuid
import requests

from airflow.sdk import dag, task
from sqlalchemy import and_, or_, select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from toolmeta_harvester.config import egi_llm_api_key
from toolmeta_harvester.db.engine import engine

from toolmeta_harvester.db.models import Base, ToolMetadata, ToolEmbedding
from toolmeta_harvester.tasks import embedding


EMBEDDING_MODEL = "nomic-embed-text-v2-moe"
EMBEDDING_TYPE = "description"
EMBEDDING_API = "https://llm.ai.egi.eu/embeddings"

BATCH_SIZE = 10
EGI_LLM_API_KEY = egi_llm_api_key()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dag(
    dag_id="toolmeta_embedding_raw",
    schedule=None,
    catchup=False,
    max_active_tasks=10,
    tags=["embedding"],
)
def embed_descriptions():

    Base.metadata.create_all(engine)

    @task
    def create_batches() -> list[list[str]]:
        """
        Find tools whose description embedding is missing or stale.

        An embedding is stale when:
        - no embedding exists, or
        - ToolMetadata.date_modified > ToolEmbedding.created_at
        """

        with Session(engine) as session:
            stmt = (
                select(ToolMetadata.id)
                .outerjoin(
                    ToolEmbedding,
                    and_(
                        ToolEmbedding.tool_id == ToolMetadata.id,
                        ToolEmbedding.embedding_type == EMBEDDING_TYPE,
                        ToolEmbedding.embedding_model == EMBEDDING_MODEL,
                    ),
                )
                .where(
                    ToolMetadata.description.is_not(None),
                    or_(
                        # Never embedded
                        ToolEmbedding.id.is_(None),
                        # Source metadata changed after embedding
                        ToolMetadata.date_modified > ToolEmbedding.created_at,
                    ),
                )
                .order_by(ToolMetadata.id)
            )

            tool_ids = session.scalars(stmt).all()

        ids = [str(tool_id) for tool_id in tool_ids]

        # return [ids[i : i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]
        return [ids[:BATCH_SIZE]]

    @task
    def embed_batch(tool_ids: list[str]) -> int:
        ids = [uuid.UUID(tool_id) for tool_id in tool_ids]

        with Session(engine) as session:
            records = session.scalars(
                select(ToolMetadata)
                .where(ToolMetadata.id.in_(ids))
                .order_by(ToolMetadata.id)
            ).all()

            records = [record for record in records if record.description]

            if not records:
                return 0

            # ---------------------------------------------------------
            # Generate description embeddings
            # ---------------------------------------------------------

            vectors = embedding.embed(
                [record.description for record in records],
                api_key=EGI_LLM_API_KEY,
                api_url=EMBEDDING_API,
                model=EMBEDDING_MODEL,
                prefix="search_document: ",
            )

            if len(vectors) != len(records):
                raise RuntimeError(
                    f"Embedding API returned {len(vectors)} vectors "
                    f"for {len(records)} records"
                )

            # ---------------------------------------------------------
            # Prepare rows
            # ---------------------------------------------------------

            values = [
                {
                    "tool_id": record.id,
                    "embedding_type": EMBEDDING_TYPE,
                    "embedding_model": EMBEDDING_MODEL,
                    # Store the original text, not the prefixed/truncated text.
                    "text": record.description,
                    "vector": vector,
                }
                for record, vector in zip(records, vectors)
            ]

            # ---------------------------------------------------------
            # Bulk UPSERT
            # ---------------------------------------------------------

            stmt = insert(ToolEmbedding).values(values)

            stmt = stmt.on_conflict_do_update(
                constraint="uq_tool_embedding",
                set_={
                    "text": stmt.excluded.text,
                    "vector": stmt.excluded.vector,
                    "created_at": func.now(),
                },
            )

            session.execute(stmt)
            session.commit()

            return len(values)

    # @task
    # def embed_batch(tool_ids: list[str]) -> int:
    #
    #     ids = [uuid.UUID(tool_id) for tool_id in tool_ids]
    #
    #     with Session(engine) as session:
    #         records = session.scalars(
    #             select(ToolMetadata)
    #             .where(ToolMetadata.id.in_(ids))
    #             .order_by(ToolMetadata.id)
    #         ).all()
    #
    #         records = [record for record in records if record.description]
    #
    #         if not records:
    #             return 0
    #
    #         # -----------------------------------------------------
    #         # Generate embeddings in one API request
    #         # -----------------------------------------------------
    #
    #         response = requests.post(
    #             EMBEDDING_API,
    #             headers={
    #                 "Authorization": f"Bearer {EGI_LLM_API_KEY}",
    #                 "Content-Type": "application/json",
    #             },
    #             json={
    #                 "model": EMBEDDING_MODEL,
    #                 "input": [record.description for record in records],
    #             },
    #             timeout=120,
    #         )
    #
    #         response.raise_for_status()
    #
    #         results = sorted(
    #             response.json()["data"],
    #             key=lambda result: result["index"],
    #         )
    #
    #         if len(results) != len(records):
    #             raise RuntimeError(
    #                 f"Embedding API returned {len(results)} embeddings "
    #                 f"for {len(records)} inputs"
    #             )
    #
    #         # -----------------------------------------------------
    #         # Prepare rows
    #         # -----------------------------------------------------
    #
    #         values = [
    #             {
    #                 "tool_id": record.id,
    #                 "embedding_type": EMBEDDING_TYPE,
    #                 "embedding_model": EMBEDDING_MODEL,
    #                 "text": record.description,
    #                 # "text_hash": text_hash(record.description),
    #                 "vector": result["embedding"],
    #             }
    #             for record, result in zip(records, results)
    #         ]
    #
    #         # -----------------------------------------------------
    #         # Idempotent bulk UPSERT
    #         # -----------------------------------------------------
    #
    #         stmt = insert(ToolEmbedding).values(values)
    #
    #         stmt = stmt.on_conflict_do_update(
    #             constraint="uq_tool_embedding",
    #             set_={
    #                 "text": stmt.excluded.text,
    #                 # "text_hash": stmt.excluded.text_hash,
    #                 "vector": stmt.excluded.vector,
    #                 "created_at": func.now(),
    #             },
    #         )
    #
    #         session.execute(stmt)
    #         session.commit()
    #
    #         return len(values)

    batches = create_batches()

    embed_batch.expand(
        tool_ids=batches,
    )


embed_descriptions()
