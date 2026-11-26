from typing import Any, Protocol

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import get_settings


class Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


COLLECTION_NAME = "repomind_code"


class RetrievalService:
    def __init__(self, embedder: Embedder, client: QdrantClient | None = None) -> None:
        settings = get_settings()
        self.embedder = embedder
        self.client = client or QdrantClient(path=settings.qdrant_path)

    def retrieve(
        self,
        query: str,
        repository_id: int,
        commit_sha: str,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        vector = self.embedder.embed_query(query)
        try:
            self.client.get_collection(COLLECTION_NAME)
        except Exception:
            return []

        result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_id",
                        match=models.MatchValue(value=repository_id),
                    ),
                    models.FieldCondition(
                        key="commit_sha",
                        match=models.MatchValue(value=commit_sha),
                    ),
                ]
            ),
        )
        return [
            {"score": point.score, "payload": point.payload or {}}
            for point in result.points
        ]
