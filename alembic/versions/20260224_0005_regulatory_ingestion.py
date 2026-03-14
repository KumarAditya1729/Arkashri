# pyre-ignore-all-errors
"""regulatory ingestion sources and documents

Revision ID: 20260224_0005
Revises: 20260224_0004
Create Date: 2026-02-24 02:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260224_0005"
down_revision: Union[str, None] = "20260224_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

regulatory_source_type_enum = postgresql.ENUM(
    "API_JSON",
    "RSS",
    "HTML",
    "MANUAL",
    name="regulatory_source_type",
    create_type=False,
)
ingest_run_status_enum = postgresql.ENUM(
    "STARTED",
    "SUCCESS",
    "FAILED",
    name="ingest_run_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    regulatory_source_type_enum.create(bind, checkfirst=True)
    ingest_run_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "regulatory_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("authority", sa.String(length=120), nullable=False),
        sa.Column("source_type", regulatory_source_type_enum, nullable=False),
        sa.Column("endpoint", sa.String(length=1024), nullable=False),
        sa.Column("parser_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_key", name="uq_regulatory_source_key"),
    )

    op.create_table(
        "regulatory_ingest_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("status", ingest_run_status_enum, nullable=False, server_default="STARTED"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["regulatory_source.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "regulatory_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("authority", sa.String(length=120), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("document_url", sa.String(length=2048), nullable=False),
        sa.Column("published_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_promoted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("promoted_knowledge_doc_id", sa.Integer(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["regulatory_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promoted_knowledge_doc_id"], ["knowledge_document.id"]),
        sa.UniqueConstraint("source_id", "external_id", name="uq_regulatory_document_external"),
    )

    op.create_index(
        "ix_regulatory_source_scope_active",
        "regulatory_source",
        ["jurisdiction", "authority", "is_active"],
    )
    op.create_index(
        "ix_regulatory_ingest_run_source_started",
        "regulatory_ingest_run",
        ["source_id", "started_at"],
    )
    op.create_index(
        "ix_regulatory_document_scope_published",
        "regulatory_document",
        ["jurisdiction", "authority", "published_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_regulatory_document_scope_published", table_name="regulatory_document")
    op.drop_index("ix_regulatory_ingest_run_source_started", table_name="regulatory_ingest_run")
    op.drop_index("ix_regulatory_source_scope_active", table_name="regulatory_source")

    op.drop_table("regulatory_document")
    op.drop_table("regulatory_ingest_run")
    op.drop_table("regulatory_source")

    bind = op.get_bind()
    ingest_run_status_enum.drop(bind, checkfirst=True)
    regulatory_source_type_enum.drop(bind, checkfirst=True)
