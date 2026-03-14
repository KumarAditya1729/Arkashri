# pyre-ignore-all-errors
"""security clients and idempotency records

Revision ID: 20260224_0004
Revises: 20260223_0003
Create Date: 2026-02-24 00:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260224_0004"
down_revision: Union[str, None] = "20260223_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

client_role_enum = postgresql.ENUM(
    "ADMIN",
    "OPERATOR",
    "REVIEWER",
    "READ_ONLY",
    name="client_role",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    client_role_enum.create(bind, checkfirst=True)

    op.create_table(
        "api_client",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", client_role_enum, nullable=False, server_default="READ_ONLY"),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_api_client_key_hash"),
    )

    op.create_table(
        "idempotency_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["decision_id"], ["decision.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "jurisdiction", "idempotency_key", name="uq_idempotency_scope_key"),
    )

    op.create_index("ix_api_client_role_active", "api_client", ["role", "is_active"])
    op.create_index(
        "ix_idempotency_scope_created",
        "idempotency_record",
        ["tenant_id", "jurisdiction", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_scope_created", table_name="idempotency_record")
    op.drop_index("ix_api_client_role_active", table_name="api_client")
    op.drop_table("idempotency_record")
    op.drop_table("api_client")

    bind = op.get_bind()
    client_role_enum.drop(bind, checkfirst=True)
