# pyre-ignore-all-errors
"""
Alembic Migration: Platform Sessions
====================================
Creates a DB-backed session ledger for rotating refresh tokens and
immediate server-side revocation.

Revision: 20260419_0011
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260419_0011"
down_revision = "20260228_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_session",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(120), nullable=True),
        sa.Column("replaced_by_session_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["platform_user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_platform_session_refresh_hash"),
    )
    op.create_index("ix_platform_session_user_active", "platform_session", ["user_id", "revoked_at"])
    op.create_index("ix_platform_session_family", "platform_session", ["family_id"])
    op.create_index("ix_platform_session_tenant_user", "platform_session", ["tenant_id", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_session_tenant_user", table_name="platform_session")
    op.drop_index("ix_platform_session_family", table_name="platform_session")
    op.drop_index("ix_platform_session_user_active", table_name="platform_session")
    op.drop_table("platform_session")
