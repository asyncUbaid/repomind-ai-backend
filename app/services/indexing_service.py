import hashlib
import uuid
import asyncio
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import get_settings
from app.db.models import Repository, RepositoryFile
from app.services.github_service import GitHubService
from app.services.parser_service import language_for_path, parse_chunks, should_index_file
from app.ai.models import create_embeddings

COLLECTION_NAME = "repomind_code"


def delete_repository_vectors(repository_id: int) -> None:
    client = QdrantClient(path=get_settings().qdrant_path)
    try:
        if not client.collection_exists(COLLECTION_NAME):
            return
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repository_id",
                            match=models.MatchValue(value=repository_id),
                        )
                    ]
                )
            ),
            wait=True,
        )
    finally:
        client.close()


class IndexingService:
    def __init__(self, github: GitHubService) -> None:
        self.github = github
        self.settings = get_settings()
        self.embeddings = create_embeddings()
        self.qdrant = QdrantClient(path=self.settings.qdrant_path)
        self.llm_semaphore = asyncio.Semaphore(1)

    async def _upsert_chunks(self, chunks: list, repository: Repository) -> None:
        if not chunks:
            return
        await self.llm_semaphore.acquire()
        try:
            vectors = self.embeddings.embed_documents([chunk.content for chunk in chunks])
        finally:
            self.llm_semaphore.release()
        if not vectors:
            return
        try:
            self.qdrant.get_collection(COLLECTION_NAME)
        except Exception:
            self.qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=len(vectors[0]),
                    distance=models.Distance.COSINE,
                ),
            )

        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repository.id}:{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:{chunk.content_hash}:{repository.latest_commit_sha}")),
                vector=vector,
                payload={
                    "repository_id": repository.id,
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "symbol_name": chunk.symbol_name,
                    "commit_sha": repository.latest_commit_sha,
                    "content": chunk.content,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self.qdrant.upsert(collection_name=COLLECTION_NAME, points=points)

    async def index_repository(self, repository: Repository, owner: str, db: Session) -> int:
        repository.status = "processing"
        db.commit()
        try:
            tree = await self.github.get_file_tree(owner, repository.name, repository.latest_commit_sha or repository.default_branch)
            if len(tree) > self.settings.max_repository_files:
                raise ValueError("Repository exceeds the configured file limit")
            try:
                self.qdrant.get_collection(COLLECTION_NAME)
                self.qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="repository_id",
                                    match=models.MatchValue(value=repository.id),
                                )
                            ]
                        )
                    ),
                )
            except Exception:
                pass
            indexed = 0
            for item in tree:
                path = item.get("path")
                size = int(item.get("size", 0))
                if not isinstance(path, str) or not should_index_file(
                    path, size, self.settings.max_file_size_bytes
                ):
                    continue
                content = await self.github.get_file_content(
                    owner,
                    repository.name,
                    path,
                    repository.latest_commit_sha or repository.default_branch,
                )
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                language = language_for_path(path)

                existing = db.scalar(
                    select(RepositoryFile).where(
                        RepositoryFile.repository_id == repository.id,
                        RepositoryFile.file_path == path,
                    )
                )
                if existing is not None and existing.content_hash == content_hash:
                    continue
                if existing is not None:
                    existing.content_hash = content_hash
                    existing.language = language
                    existing.total_lines = len(content.splitlines())
                else:
                    db.add(
                        RepositoryFile(
                            repository_id=repository.id,
                            file_path=path,
                            file_path_hash=hashlib.sha256(path.encode("utf-8")).hexdigest(),
                            language=language,
                            content_hash=content_hash,
                            total_lines=len(content.splitlines()),
                        )
                    )
                chunks = parse_chunks(content, path, language or "text")
                await self._upsert_chunks(chunks, repository)
                indexed += 1

            db.commit()
            repository.status = "completed"
            db.commit()
            return indexed
        except Exception:
            repository.status = "failed"
            db.commit()
            raise
