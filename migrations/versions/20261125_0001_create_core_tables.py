"""Create core RepoMind tables.

Revision ID: 20261125_0001
Revises:
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "20261125_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        existing_tables.add("users")

    if "repositories" not in existing_tables:
        op.create_table(
            "repositories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("github_repo_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(512), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("default_branch", sa.String(255), nullable=False),
            sa.Column("latest_commit_sha", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "github_repo_id", name="uq_repository_owner_github"),
        )
        existing_tables.add("repositories")
    if "ix_repositories_full_name" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("repositories")
    }:
        op.create_index("ix_repositories_full_name", "repositories", ["full_name"])

    if "repository_files" not in existing_tables:
        op.create_table(
            "repository_files",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repository_id", sa.Integer(), nullable=False),
            sa.Column("file_path", sa.String(1024), nullable=False),
            sa.Column("file_path_hash", sa.String(64), nullable=False),
            sa.Column("language", sa.String(64), nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("total_lines", sa.Integer(), nullable=False),
            sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("repository_id", "file_path_hash", name="uq_repository_file_path"),
        )
        existing_tables.add("repository_files")
    if "ix_repository_files_repository" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("repository_files")
    }:
        op.create_index("ix_repository_files_repository", "repository_files", ["repository_id"])

    if "conversations" not in existing_tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("repository_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        )
        existing_tables.add("conversations")
    if "messages" not in existing_tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", mysql.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        )
        existing_tables.add("messages")
    if "analysis_reports" not in existing_tables:
        op.create_table(
            "analysis_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repository_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("report_type", sa.String(64), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("report_data", mysql.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )


def downgrade() -> None:
    op.drop_table("analysis_reports")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_index("ix_repository_files_repository", "repository_files")
    op.drop_table("repository_files")
    op.drop_index("ix_repositories_full_name", "repositories")
    op.drop_table("repositories")
    op.drop_table("users")
