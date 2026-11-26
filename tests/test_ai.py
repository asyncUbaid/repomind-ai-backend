from app.services.retrieval_service import COLLECTION_NAME


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        assert text
        return [0.1, 0.2, 0.3]


class FakeQdrant:
    def get_collection(self, name: str) -> object:
        assert name == COLLECTION_NAME
        return object()

    def query_points(self, **kwargs):
        assert kwargs["limit"] == 3
        assert kwargs["query"] == [0.1, 0.2, 0.3]

        class Point:
            score = 0.92
            payload = {
                "repository_id": 7,
                "commit_sha": "abc123",
                "file_path": "src/auth.py",
                "start_line": 20,
                "end_line": 45,
                "symbol_name": "validateUser",
                "content": "def validateUser(): pass",
            }

        class Result:
            points = [Point()]

        return Result()


def test_retrieval_filters_repository_and_commit() -> None:
    from app.services.retrieval_service import RetrievalService

    service = RetrievalService(embedder=FakeEmbedder(), client=FakeQdrant())  # type: ignore[arg-type]
    results = service.retrieve(
        "How does authentication work?",
        repository_id=7,
        commit_sha="abc123",
        limit=3,
    )
    assert results[0]["payload"]["file_path"] == "src/auth.py"


def test_rag_citations_are_generated_from_metadata() -> None:
    from app.api.routes.chat import generated_citations

    citations = generated_citations(
        [
            {
                "payload": {
                    "file_path": "src/auth.py",
                    "start_line": 20,
                    "end_line": 45,
                    "symbol_name": "validateUser",
                }
            }
        ]
    )
    assert citations[0].model_dump() == {
        "file_path": "src/auth.py",
        "start_line": 20,
        "end_line": 45,
        "symbol_name": "validateUser",
    }


def test_feature_impact_report_validation() -> None:
    from app.schemas.analysis import FeatureImpactReport

    report = FeatureImpactReport(
        feature_request="Add Google OAuth",
        summary="The authentication flow may need extension.",
        affected_files=[
            {
                "file_path": "src/auth/auth.service.ts",
                "impact_level": "high",
                "impact_basis": "direct_observed",
                "reason": "Contains existing authentication logic.",
                "recommended_changes": ["Add OAuth token validation."],
                "evidence": [{"start_line": 20, "end_line": 65}],
            }
        ],
        implementation_steps=["Add provider configuration."],
        risks=["OAuth callback URLs must be secured."],
        assumptions=["The application uses an external identity provider."],
    )
    assert report.affected_files[0].impact_basis == "direct_observed"


def test_delete_repository_vectors_only_removes_matching_repository(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from qdrant_client import QdrantClient, models

    from app.services import indexing_service

    qdrant_path = tmp_path / "qdrant"
    client = QdrantClient(path=str(qdrant_path))
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(id=1, vector=[0.1, 0.2], payload={"repository_id": 7}),
            models.PointStruct(id=2, vector=[0.2, 0.3], payload={"repository_id": 8}),
        ],
    )
    client.close()

    monkeypatch.setattr(
        indexing_service,
        "get_settings",
        lambda: SimpleNamespace(qdrant_path=str(qdrant_path)),
    )
    indexing_service.delete_repository_vectors(7)

    client = QdrantClient(path=str(qdrant_path))
    points, _ = client.scroll(collection_name=COLLECTION_NAME, limit=10, with_payload=True)
    client.close()
    assert [point.payload["repository_id"] for point in points] == [8]
