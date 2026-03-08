"""
Alembic Migration: Platform Users Table
========================================
Creates:
  - user_role   ENUM (ADMIN, OPERATOR, REVIEWER, READ_ONLY)
  - platform_user table (tenant-scoped user accounts with bcrypt passwords)

Revision: 20260228_0010
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision      = "20260228_0010"
down_revision = "20260226_0009"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Enum created automatically by SQLAlchemy create_table

    op.create_table(
        "platform_user",
        sa.Column("id",              sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id",       sa.String(100),  nullable=False),
        sa.Column("email",           sa.String(255),  nullable=False),
        sa.Column("hashed_password", sa.String(255),  nullable=False),
        sa.Column("full_name",       sa.String(255),  nullable=False),
        sa.Column("initials",        sa.String(10),   nullable=False, server_default="?"),
        sa.Column("role",            sa.Enum("ADMIN","OPERATOR","REVIEWER","READ_ONLY",
                                            name="user_role"), nullable=False,
                  server_default="REVIEWER"),
        sa.Column("is_active",       sa.Boolean,      nullable=False, server_default="true"),
        sa.Column("last_login_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by",      sa.String(255),  nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_tenant_user_email"),
    )
    op.create_index("ix_platform_user_tenant_email", "platform_user", ["tenant_id", "email"])
    op.create_index("ix_platform_user_tenant_active", "platform_user", ["tenant_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_platform_user_tenant_active", "platform_user")
    op.drop_index("ix_platform_user_tenant_email",  "platform_user")
    op.drop_table("platform_user")
    op.execute("DROP TYPE IF EXISTS user_role")
