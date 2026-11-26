import base64
import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.core.config import get_settings

GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_github_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Repository must be a valid github.com URL")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("Repository URL must include owner and repository name")
    owner, repository = parts[0], parts[1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    candidate = f"{owner}/{repository}"
    if not GITHUB_REPOSITORY_PATTERN.fullmatch(candidate):
        raise ValueError("Invalid GitHub owner or repository name")
    return owner, repository


class GitHubService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = client
        self.headers = headers
        self.timeout = settings.ollama_request_timeout_seconds

    async def _get(self, url: str) -> Any:
        if self.client is not None:
            response = await self.client.get(url, headers=self.headers)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
        if response.status_code == 404:
            raise ValueError("GitHub repository or resource was not found")
        if response.status_code == 403:
            raise ValueError("GitHub API rate limit exceeded or access denied")
        if response.status_code >= 400:
            raise ValueError(f"GitHub API request failed with status {response.status_code}")
        return response.json()

    async def get_repository(self, owner: str, repository: str) -> dict[str, Any]:
        return await self._get(f"https://api.github.com/repos/{owner}/{repository}")

    async def get_file_tree(self, owner: str, repository: str, commit_sha: str) -> list[dict[str, Any]]:
        data = await self._get(
            f"https://api.github.com/repos/{owner}/{repository}/git/trees/{commit_sha}?recursive=1"
        )
        if data.get("truncated"):
            raise ValueError("GitHub repository tree is too large to index safely")
        return [item for item in data.get("tree", []) if item.get("type") == "blob"]

    async def get_file_content(self, owner: str, repository: str, path: str, ref: str) -> str:
        data = await self._get(
            f"https://api.github.com/repos/{owner}/{repository}/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}",
        )
        content = data.get("content")
        encoding = data.get("encoding")
        if encoding == "base64" and isinstance(content, str):
            return base64.b64decode(content).decode("utf-8", errors="replace")
        raise ValueError(f"Unable to retrieve text content for {path}")

    async def get_branch_commit(self, owner: str, repository: str, branch: str) -> str:
        data = await self._get(
            f"https://api.github.com/repos/{owner}/{repository}/branches/{quote(branch, safe='')}"
        )
        return str(data["commit"]["sha"])
