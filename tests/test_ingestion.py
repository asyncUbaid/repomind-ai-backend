import pytest
import asyncio
import httpx

from app.services.github_service import parse_github_url
from app.services.parser_service import parse_chunks, should_index_file
from app.services.github_service import GitHubService


def test_parse_github_url() -> None:
    assert parse_github_url("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
    with pytest.raises(ValueError):
        parse_github_url("https://example.com/octocat/Hello-World")


def test_file_filtering() -> None:
    assert should_index_file("src/auth.py", 100, 1_000_000)
    assert not should_index_file("node_modules/pkg/index.js", 100, 1_000_000)
    assert not should_index_file("package-lock.json", 100, 1_000_000)
    assert not should_index_file("src/huge.py", 2_000_000, 1_000_000)


def test_synthetic_python_chunking() -> None:
    content = (
        "def validate_user(token: str):\n"
        "    if not token:\n"
        "        raise ValueError('missing')\n"
        "    return True\n"
    )
    chunks = parse_chunks(content, "src/auth.py", "python")
    assert chunks
    assert chunks[0].start_line == 1
    assert chunks[0].end_line >= 4
    assert chunks[0].symbol_name == "validate_user"


def test_github_repository_response_mock() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": 1, "name": "Hello-World", "full_name": "octocat/Hello-World", "default_branch": "main"},
        )

    async def run() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await GitHubService(client).get_repository("octocat", "Hello-World")

    metadata = asyncio.run(run())
    assert metadata["full_name"] == "octocat/Hello-World"
