from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from tree_sitter_language_pack import get_language, get_parser

SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
}

EXCLUDED_DIRECTORY_PARTS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "cache",
    ".cache",
    "__pycache__",
    "coverage",
    "target",
}

EXCLUDED_FILENAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
}


@dataclass(frozen=True)
class CodeChunk:
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_type: str
    symbol_name: str | None
    content: str
    content_hash: str


def language_for_path(path: str) -> str | None:
    lowered = path.lower()
    for suffix, language in SUPPORTED_LANGUAGES.items():
        if lowered.endswith(suffix):
            return language
    return None


def should_index_file(path: str, size: int, max_file_size: int) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.lower().split("/")
    if any(part in EXCLUDED_DIRECTORY_PARTS for part in parts[:-1]):
        return False
    filename = parts[-1]
    if filename in EXCLUDED_FILENAMES:
        return False
    if filename.startswith(".env"):
        return False
    if filename.endswith((".min.js", ".min.css", ".map")):
        return False
    if size > max_file_size:
        return False
    return language_for_path(normalized) is not None


def line_chunks(content: str, file_path: str, language: str, chunk_lines: int = 80, overlap: int = 20) -> list[CodeChunk]:
    lines = content.splitlines()
    if not lines:
        return []
    chunks: list[CodeChunk] = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_lines, len(lines))
        chunk_content = "\n".join(lines[start:end])
        chunks.append(
            CodeChunk(
                file_path=file_path,
                language=language,
                start_line=start + 1,
                end_line=end,
                chunk_type="lines",
                symbol_name=None,
                content=chunk_content,
                content_hash=hashlib.sha256(chunk_content.encode("utf-8")).hexdigest(),
            )
        )
        if end == len(lines):
            break
        start = max(end - overlap, start + 1)
    return chunks


def parse_chunks(content: str, file_path: str, language: str) -> list[CodeChunk]:
    if language == "markdown" or language == "json" or language == "yaml":
        return line_chunks(content, file_path, language)
    try:
        parser = get_parser(language)
    except Exception:
        return line_chunks(content, file_path, language)

    tree = parser.parse(content.encode("utf-8"))
    target_types = {
        "function_declaration",
        "method_declaration",
        "method_definition",
        "class_declaration",
        "class_definition",
        "interface_declaration",
        "arrow_function",
        "function_definition",
        "export_statement",
        "import_statement",
    }
    selected: list[tuple[int, int, str, str | None]] = []

    def walk(node) -> None:
        if node.type in target_types:
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            name = None
            for child in node.children:
                if child.type in {"identifier", "property_identifier", "type_identifier"}:
                    name = content.encode("utf-8")[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    break
            selected.append((start, end, node.type, name))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    if not selected:
        return line_chunks(content, file_path, language)

    chunks: list[CodeChunk] = []
    lines = content.splitlines()
    for start, end, node_type, name in sorted(set(selected), key=lambda item: (item[0], item[1], item[2], item[3] or "")):
        start = max(1, start)
        end = min(len(lines), end)
        chunk_content = "\n".join(lines[start - 1:end])
        chunks.append(
            CodeChunk(
                file_path=file_path,
                language=language,
                start_line=start,
                end_line=end,
                chunk_type=node_type,
                symbol_name=name,
                content=chunk_content,
                content_hash=hashlib.sha256(chunk_content.encode("utf-8")).hexdigest(),
            )
        )
    return chunks
