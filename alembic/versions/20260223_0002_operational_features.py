# pyre-ignore-all-errors
"""operational feature tables

Revision ID: 20260223_0002
Revises: 20260223_0001
Create Date: 2026-02-23 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260223_0002"
down_revision: Union[str, None] = "20260223_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

exception_status_enum = postgresql.ENUM("OPEN", "RESOLVED", "DISMISSED", name="exception_status", create_type=False)
report_status_enum = postgresql.ENUM("GENERATED", "FAILED", name="report_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    exception_status_enum.create(bind, checkfirst=True)
    report_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "exception_case",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("status", exception_status_enum, nullable=False, server_default="OPEN"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["decision.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "report_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", report_status_enum, nullable=False, server_default="GENERATED"),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "chain_anchor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("window_start_event_id", sa.Integer(), nullable=False),
        sa.Column("window_end_event_id", sa.Integer(), nullable=False),
        sa.Column("merkle_root", sa.String(length=64), nullable=False),
        sa.Column("anchor_provider", sa.String(length=100), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("agent_key", name="uq_agent_key"),
    )

    op.create_index(
        "ix_exception_case_tenant_jurisdiction_status",
        "exception_case",
        ["tenant_id", "jurisdiction", "status"],
    )
    op.create_index(
        "ix_report_job_tenant_jurisdiction_created",
        "report_job",
        ["tenant_id", "jurisdiction", "created_at"],
    )
    op.create_index(
        "ix_chain_anchor_tenant_jurisdiction_id",
        "chain_anchor",
        ["tenant_id", "jurisdiction", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chain_anchor_tenant_jurisdiction_id", table_name="chain_anchor")
    op.drop_index("ix_report_job_tenant_jurisdiction_created", table_name="report_job")
    op.drop_index("ix_exception_case_tenant_jurisdiction_status", table_name="exception_case")

    op.drop_table("agent_profile")
    op.drop_table("chain_anchor")
    op.drop_table("report_job")
    op.drop_table("exception_case")

    bind = op.get_bind()
    report_status_enum.drop(bind, checkfirst=True)
    exception_status_enum.drop(bind, checkfirst=True)
