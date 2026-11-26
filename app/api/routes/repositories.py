from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.database import get_db
from app.db.models import Repository, RepositoryFile, User
from app.schemas.repository import (
    IndexStatusResponse,
    RepositoryCreate,
    RepositoryFileResponse,
    RepositoryResponse,
)
from app.services.architecture_service import build_structure
from app.services.github_service import GitHubService, parse_github_url
from app.services.indexing_service import IndexingService, delete_repository_vectors

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def owner_repository(repository_id: int, user: User, db: Session) -> Repository:
    repository = db.scalar(
        select(Repository).where(Repository.id == repository_id, Repository.user_id == user.id)
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repository


@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Repository]:
    return list(db.scalars(select(Repository).where(Repository.user_id == current_user.id).order_by(Repository.created_at.desc())))


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def add_repository(
    payload: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Repository:
    try:
        owner, name = parse_github_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    try:
        metadata = await GitHubService().get_repository(owner, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    existing = db.scalar(
        select(Repository).where(
            Repository.user_id == current_user.id,
            Repository.github_repo_id == int(metadata["id"]),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is already connected")

    repository = Repository(
        user_id=current_user.id,
        github_repo_id=int(metadata["id"]),
        name=str(metadata["name"]),
        full_name=str(metadata["full_name"]),
        description=metadata.get("description"),
        default_branch=str(metadata["default_branch"]),
        latest_commit_sha=None,
        status="pending",
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


@router.get("/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Repository:
    return owner_repository(repository_id, current_user, db)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    repository = owner_repository(repository_id, current_user, db)
    delete_repository_vectors(repository.id)
    db.delete(repository)
    db.commit()


@router.post("/{repository_id}/index", response_model=IndexStatusResponse)
async def index_repository(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndexStatusResponse:
    repository = owner_repository(repository_id, current_user, db)
    owner = repository.full_name.split("/", 1)[0]
    try:
        metadata = await GitHubService().get_repository(owner, repository.name)
        github = GitHubService()
        repository.latest_commit_sha = await github.get_branch_commit(
            owner,
            repository.name,
            str(metadata["default_branch"]),
        )
        db.commit()
        count = await IndexingService(GitHubService()).index_repository(repository, owner, db)
    except ValueError as exc:
        repository.status = "failed"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    file_count = db.scalar(
        select(func.count(RepositoryFile.id)).where(RepositoryFile.repository_id == repository.id)
    ) or 0
    return IndexStatusResponse(
        status=repository.status,
        latest_commit_sha=repository.latest_commit_sha,
        indexed_file_count=file_count,
    )


@router.get("/{repository_id}/index-status", response_model=IndexStatusResponse)
def index_status(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndexStatusResponse:
    repository = owner_repository(repository_id, current_user, db)
    file_count = db.scalar(
        select(func.count(RepositoryFile.id)).where(RepositoryFile.repository_id == repository.id)
    ) or 0
    return IndexStatusResponse(
        status=repository.status,
        latest_commit_sha=repository.latest_commit_sha,
        indexed_file_count=file_count,
    )


@router.get("/{repository_id}/files", response_model=list[RepositoryFileResponse])
def list_files(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RepositoryFile]:
    repository = owner_repository(repository_id, current_user, db)
    return list(
        db.scalars(
            select(RepositoryFile)
            .where(RepositoryFile.repository_id == repository.id)
            .order_by(RepositoryFile.file_path)
        )
    )


@router.get("/{repository_id}/structure")
def structure(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    repository = owner_repository(repository_id, current_user, db)
    return build_structure(repository, db)
