# RepoMind AI Backend

The RepoMind AI backend is a FastAPI service for authentication, GitHub repository ingestion, code indexing, local retrieval, chat, and impact analysis.

## Technology

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- MySQL Community Edition
- LangChain
- Ollama
- Embedded local Qdrant
- JWT authentication

## Prerequisites

- Python 3.12
- MySQL Community Edition
- Ollama
- An optional GitHub personal access token

## Repository Status

The backend source code, dependency manifest, environment template, migrations, and tests have not been added to this directory yet. The setup and commands below describe the intended FastAPI application and should be used after the backend scaffold is created.

## Setup

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a local environment file once `.env.example` is available:

```bash
cp .env.example .env
```

Configure MySQL, Ollama, and optional GitHub credentials in `.env`. Keep local credentials out of source control.

Apply database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Local AI Setup

Start Ollama and download the intended models:

```bash
ollama serve
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3-embedding:0.6b
```

Model names and runtime settings should remain configurable through the backend environment.

## Database

MySQL stores users, repositories, files, conversations, messages, and analysis reports. Alembic migrations should be the only mechanism used to change the database schema.

Create a migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## API

Health check:

```http
GET /health
```

Authentication:

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

Repository, chat, structure, and impact-analysis routes are documented in [the API reference](../docs/api.md).

Protected routes require a JWT bearer token:

```http
Authorization: Bearer <token>
```

## Tests

After tests are added:

```bash
python -m pytest -q
```

Run formatting and linting with the tools configured in the project, for example:

```bash
ruff check .
ruff format --check .
python -m mypy app
```

Use only project-configured commands if a tool is not present in `requirements.txt`.

## Project Layout

The intended structure is:

```text
backend/
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   └── services/
├── alembic/
├── tests/
├── .env.example
└── requirements.txt
```

Repository source should be filtered and chunked before indexing. Source files must not be executed during ingestion or analysis. Local Qdrant data belongs in `qdrant_data/`, which is excluded from source control.
