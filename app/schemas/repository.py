from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    full_name: str
    description: str | None
    default_branch: str
    latest_commit_sha: str | None
    status: str
    created_at: datetime


class RepositoryFileResponse(BaseModel):
    id: int
    file_path: str
    language: str | None
    content_hash: str
    total_lines: int
    indexed_at: datetime


class IndexStatusResponse(BaseModel):
    status: str
    latest_commit_sha: str | None
    indexed_file_count: int
