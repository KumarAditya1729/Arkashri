# pyre-ignore-all-errors
"""
Alembic Migration: Audit Operationalization
===========================================
Adds evidence management infrastructure and explainability trace logs.
1. Creates 'evidence_record' table.
2. Creates 'transaction_evidence_map' M2M table.
3. Adds 'trace_log' column to 'decision' table.

Revision: 20260419_0012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260419_0012"
down_revision = "20260419_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create evidence_record table
    op.create_table(
        "evidence_record",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("file_key", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(50), server_default="S3"),
        sa.Column("storage_tier", sa.String(50), server_default="STANDARD"),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # 2. Create transaction_evidence_map M2M table
    op.create_table(
        "transaction_evidence_map",
        sa.Column("transaction_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("linked_by", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["financial_transaction.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("transaction_id", "evidence_id")
    )

    # 3. Add trace_log to decision table
    op.add_column("decision", sa.Column("trace_log", sa.dialects.postgresql.JSONB(), server_default="[]"))


def downgrade() -> None:
    op.drop_column("decision", "trace_log")
    op.drop_table("transaction_evidence_map")
    op.drop_table("evidence_record")
