from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import repositories as repository_routes
from app.db.database import get_db
from app.db.models import AnalysisReport, Base, Conversation, Message, Repository, RepositoryFile, User
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def test_register_login_and_me() -> None:
    register = client.post(
        "/api/auth/register",
        json={"name": "Ada Lovelace", "email": "ada@example.com", "password": "correct-horse"},
    )
    assert register.status_code == 201
    assert register.json()["email"] == "ada@example.com"

    login = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Ada Lovelace"


def test_duplicate_email_and_invalid_login() -> None:
    register = client.post(
        "/api/auth/register",
        json={"name": "Ada", "email": "duplicate@example.com", "password": "correct-horse"},
    )
    assert register.status_code == 201
    duplicate = client.post(
        "/api/auth/register",
        json={"name": "Ada 2", "email": "duplicate@example.com", "password": "correct-horse"},
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/auth/login",
        json={"email": "duplicate@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401


def test_repository_ownership_check() -> None:
    owner_register = client.post(
        "/api/auth/register",
        json={"name": "Owner", "email": "owner@example.com", "password": "correct-horse"},
    )
    assert owner_register.status_code == 201
    owner_login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    owner_token = owner_login.json()["access_token"]

    db = TestingSessionLocal()
    owner = db.scalar(select(User).where(User.email == "owner@example.com"))
    repository = Repository(
        user_id=owner.id,
        github_repo_id=12345,
        name="owned-repo",
        full_name="owner/owned-repo",
        default_branch="main",
        status="pending",
    )
    db.add(repository)
    db.commit()
    repository_id = repository.id
    db.close()

    owned = client.get(
        f"/api/repositories/{repository_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owned.status_code == 200

    other_register = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "correct-horse"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "correct-horse"},
    )
    not_owned = client.get(
        f"/api/repositories/{repository_id}",
        headers={"Authorization": f"Bearer {other_login.json()['access_token']}"},
    )
    assert not_owned.status_code == 404


def test_delete_repository_removes_owned_data(monkeypatch) -> None:
    owner_register = client.post(
        "/api/auth/register",
        json={"name": "Delete Owner", "email": "delete-owner@example.com", "password": "correct-horse"},
    )
    assert owner_register.status_code == 201
    owner_login = client.post(
        "/api/auth/login",
        json={"email": "delete-owner@example.com", "password": "correct-horse"},
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

    other_register = client.post(
        "/api/auth/register",
        json={"name": "Delete Other", "email": "delete-other@example.com", "password": "correct-horse"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "delete-other@example.com", "password": "correct-horse"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    db = TestingSessionLocal()
    owner = db.scalar(select(User).where(User.email == "delete-owner@example.com"))
    repository = Repository(
        user_id=owner.id,
        github_repo_id=54321,
        name="delete-repo",
        full_name="delete-owner/delete-repo",
        default_branch="main",
        status="completed",
    )
    db.add(repository)
    db.flush()
    conversation = Conversation(
        user_id=owner.id,
        repository_id=repository.id,
        title="Test conversation",
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="Test answer",
            citations=[],
        )
    )
    db.add(
        AnalysisReport(
            repository_id=repository.id,
            user_id=owner.id,
            report_type="feature_impact",
            query="Test feature",
            report_data={"summary": "Test"},
        )
    )
    db.add(
        RepositoryFile(
            repository_id=repository.id,
            file_path="src/main.py",
            file_path_hash="a" * 64,
            language="python",
            content_hash="b" * 64,
            total_lines=1,
        )
    )
    db.commit()
    repository_id = repository.id
    db.close()

    deleted_vectors: list[int] = []
    monkeypatch.setattr(
        repository_routes,
        "delete_repository_vectors",
        lambda repository_id: deleted_vectors.append(repository_id),
    )

    forbidden = client.delete(f"/api/repositories/{repository_id}", headers=other_headers)
    assert forbidden.status_code == 404
    assert deleted_vectors == []

    response = client.delete(f"/api/repositories/{repository_id}", headers=owner_headers)
    assert response.status_code == 204
    assert deleted_vectors == [repository_id]
    assert client.get(f"/api/repositories/{repository_id}", headers=owner_headers).status_code == 404

    db = TestingSessionLocal()
    assert db.scalar(select(Conversation).where(Conversation.repository_id == repository_id)) is None
    assert db.scalar(select(AnalysisReport).where(AnalysisReport.repository_id == repository_id)) is None
    assert db.scalar(select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)) is None
    db.close()
