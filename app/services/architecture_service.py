from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Repository, RepositoryFile


def build_structure(repository: Repository, db: Session) -> dict:
    files = db.scalars(
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repository.id)
        .order_by(RepositoryFile.file_path)
    ).all()

    language_counts = Counter(file.language for file in files if file.language)
    tree: dict[str, object] = {}
    for file in files:
        parts = file.file_path.split("/")
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})  # type: ignore[assignment]
        current.setdefault("_files", []).append(parts[-1])  # type: ignore[union-attr]

    important = [
        file.file_path
        for file in files
        if file.file_path.lower().endswith(
            ("readme.md", "package.json", "pyproject.toml", "requirements.txt", "dockerfile")
        )
    ]
    return {
        "repository": repository.full_name,
        "default_branch": repository.default_branch,
        "languages": dict(sorted(language_counts.items())),
        "important_files": important,
        "structure": tree,
        "file_count": len(files),
    }
