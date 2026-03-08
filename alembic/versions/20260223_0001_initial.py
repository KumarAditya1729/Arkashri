"""initial schema

Revision ID: 20260223_0001
Revises:
Create Date: 2026-02-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260223_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

signal_type_enum = postgresql.ENUM("DETERMINISTIC", "ML", "TREND", name="signal_type", create_type=False)
model_status_enum = postgresql.ENUM("SHADOW", "ACTIVE", "SUSPENDED", "RETIRED", name="model_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    signal_type_enum.create(bind, checkfirst=True)
    model_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "rule_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expression", sa.JSON(), nullable=False),
        sa.Column("signal_value", sa.Float(), nullable=False, server_default="1"),
        sa.Column("severity_floor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_key", "version", name="uq_rule_key_version"),
    )

    op.create_table(
        "formula_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("formula_text", sa.Text(), nullable=False),
        sa.Column("formula_hash", sa.String(length=64), nullable=False),
        sa.Column("component_caps", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "weight_set",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("weight_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "weight_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("weight_set_id", sa.Integer(), nullable=False),
        sa.Column("signal_type", signal_type_enum, nullable=False),
        sa.Column("signal_key", sa.String(length=128), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["weight_set_id"], ["weight_set.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("weight_set_id", "signal_type", "signal_key", name="uq_weight_key"),
    )

    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("hyperparams_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("feature_schema_hash", sa.String(length=64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("fairness_metrics", sa.JSON(), nullable=False),
        sa.Column("status", model_status_enum, nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=False, server_default="0"),
        sa.Column("upper_bound", sa.Float(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("model_key", "version", name="uq_model_key_version"),
    )

    op.create_table(
        "financial_transaction",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("final_risk", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("weight_set_version", sa.Integer(), nullable=False),
        sa.Column("model_versions", sa.JSON(), nullable=False),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["transaction_id"], ["financial_transaction.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("signature_key_id", sa.String(length=128), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_txn_tenant_jurisdiction_created",
        "financial_transaction",
        ["tenant_id", "jurisdiction", "created_at"],
    )
    op.create_index("ix_audit_stream", "audit_event", ["tenant_id", "jurisdiction", "id"])


def downgrade() -> None:
    op.drop_index("ix_audit_stream", table_name="audit_event")
    op.drop_index("ix_txn_tenant_jurisdiction_created", table_name="financial_transaction")

    op.drop_table("audit_event")
    op.drop_table("decision")
    op.drop_table("financial_transaction")
    op.drop_table("model_registry")
    op.drop_table("weight_entry")
    op.drop_table("weight_set")
    op.drop_table("formula_registry")
    op.drop_table("rule_registry")

    bind = op.get_bind()
    model_status_enum.drop(bind, checkfirst=True)
    signal_type_enum.drop(bind, checkfirst=True)
