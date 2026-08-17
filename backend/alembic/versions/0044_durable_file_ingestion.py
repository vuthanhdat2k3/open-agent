"""Add durable backend-owned file ingestion jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0044_durable_file_ingestion"
down_revision: str | None = "0043_task_triggered_by_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("uploaded_files") as batch:
        batch.add_column(sa.Column("file_sha256", sa.String(length=64), nullable=True))
    op.create_index("ix_uploaded_files_file_sha256", "uploaded_files", ["file_sha256"], unique=False)

    op.create_table(
        "file_ingest_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("rag_document_id", sa.String(length=256), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("parser_name", sa.String(length=128), nullable=True),
        sa.Column("parser_version", sa.String(length=128), nullable=True),
        sa.Column("pdf_classification", sa.String(length=64), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("ocr_engine", sa.String(length=64), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_ingest_jobs_org_id", "file_ingest_jobs", ["org_id"], unique=False)
    op.create_index("ix_file_ingest_jobs_file_id", "file_ingest_jobs", ["file_id"], unique=False)
    op.create_index("ix_file_ingest_jobs_status", "file_ingest_jobs", ["status"], unique=False)
    op.create_index("ix_file_ingest_jobs_lease_expires_at", "file_ingest_jobs", ["lease_expires_at"], unique=False)
    op.create_index("ix_file_ingest_jobs_correlation_id", "file_ingest_jobs", ["correlation_id"], unique=False)
    op.create_index("ix_file_ingest_jobs_due", "file_ingest_jobs", ["status", "available_at"], unique=False)
    op.create_index("ix_file_ingest_jobs_org_created", "file_ingest_jobs", ["org_id", "created_at"], unique=False)
    op.create_index(
        "uq_file_ingest_active_file", "file_ingest_jobs", ["file_id"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing', 'retrying')"),
        sqlite_where=sa.text("status IN ('queued', 'processing', 'retrying')"),
    )
    op.create_index(
        "uq_file_ingest_success_input", "file_ingest_jobs", ["file_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )


def downgrade() -> None:
    op.drop_index("uq_file_ingest_success_input", table_name="file_ingest_jobs")
    op.drop_index("uq_file_ingest_active_file", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_org_created", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_due", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_correlation_id", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_lease_expires_at", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_status", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_file_id", table_name="file_ingest_jobs")
    op.drop_index("ix_file_ingest_jobs_org_id", table_name="file_ingest_jobs")
    op.drop_table("file_ingest_jobs")
    op.drop_index("ix_uploaded_files_file_sha256", table_name="uploaded_files")
    with op.batch_alter_table("uploaded_files") as batch:
        batch.drop_column("file_sha256")
