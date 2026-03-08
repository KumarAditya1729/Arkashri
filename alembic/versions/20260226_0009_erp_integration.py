"""
Alembic Migration: ERP Integration Tables
==========================================
Creates:
  - erp_system      ENUM (SAP_S4HANA, ORACLE_FUSION, TALLY_PRIME, ZOHO_BOOKS, QUICKBOOKS, GENERIC_CSV)
  - erp_sync_status ENUM (IDLE, RUNNING, SUCCESS, PARTIAL, FAILED)
  - erp_connection  table (tenant-level ERP config + sync state)
  - erp_sync_log    table (per-sync audit trail)

Revision: 20260226_0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision      = "20260226_0009"
down_revision = "20260226_0008"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Enums created automatically by SQLAlchemy create_table

    # erp_connection
    op.create_table(
        "erp_connection",
        sa.Column("id",                     sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id",              sa.String(100), nullable=False),
        sa.Column("erp_system",             sa.Enum("SAP_S4HANA","ORACLE_FUSION","TALLY_PRIME","ZOHO_BOOKS","QUICKBOOKS","GENERIC_CSV", name="erp_system"), nullable=False),
        sa.Column("display_name",           sa.String(255), nullable=False),
        sa.Column("is_active",              sa.Boolean, nullable=False, server_default="true"),
        sa.Column("connection_config",      sa.JSON, nullable=False, server_default="{}"),
        sa.Column("last_synced_at",         sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status",       sa.Enum("IDLE","RUNNING","SUCCESS","PARTIAL","FAILED", name="erp_sync_status"), nullable=False, server_default="IDLE"),
        sa.Column("sync_count",             sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_records_ingested", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at",             sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at",             sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "erp_system", name="uq_tenant_erp"),
    )
    op.create_index("ix_erp_connection_tenant", "erp_connection", ["tenant_id", "erp_system"])

    # erp_sync_log
    op.create_table(
        "erp_sync_log",
        sa.Column("id",                sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connection_id",     sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_connection.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",         sa.String(100), nullable=False),
        sa.Column("erp_system",        sa.Enum("SAP_S4HANA","ORACLE_FUSION","TALLY_PRIME","ZOHO_BOOKS","QUICKBOOKS","GENERIC_CSV", name="erp_system"), nullable=False),
        sa.Column("status",            sa.Enum("IDLE","RUNNING","SUCCESS","PARTIAL","FAILED", name="erp_sync_status"), nullable=False, server_default="RUNNING"),
        sa.Column("records_submitted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_ingested",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_failed",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_flagged",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("sync_duration_ms",  sa.Integer, nullable=True),
        sa.Column("error_summary",     sa.Text, nullable=True),
        sa.Column("date_range_from",   sa.String(10), nullable=True),
        sa.Column("date_range_to",     sa.String(10), nullable=True),
        sa.Column("started_at",        sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at",      sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_erp_sync_log_connection", "erp_sync_log", ["connection_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_erp_sync_log_connection", "erp_sync_log")
    op.drop_table("erp_sync_log")
    op.drop_index("ix_erp_connection_tenant", "erp_connection")
    op.drop_table("erp_connection")
    op.execute("DROP TYPE IF EXISTS erp_sync_status")
    op.execute("DROP TYPE IF EXISTS erp_system")
