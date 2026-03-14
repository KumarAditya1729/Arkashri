# pyre-ignore-all-errors
"""
Alembic Migration: Multi-Partner Seal Architecture
===================================================
- Adds `SEALED` value to `engagement_status` enum
- Creates `seal_session_status` enum
- Creates `partner_role` enum
- Creates `seal_session` table
- Creates `seal_signature` table
- Adds context-lock columns to `audit_opinion`

Revision: 20260226_0007
Branch: head
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260226_0007"
down_revision = "b66fe5cf332c"  # last migration from find results
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add SEALED to engagement_status enum ───────────────────────────────
    # PostgreSQL ALTER TYPE ... ADD VALUE must run outside a transaction
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text(
        "ALTER TYPE engagement_status ADD VALUE IF NOT EXISTS 'SEALED';"
    ))
    conn.execute(sa.text("BEGIN"))

    # ── 4. Create seal_session table ──────────────────────────────────────────
    op.create_table(
        "seal_session",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("engagement_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("required_signatures", sa.Integer, nullable=False, server_default="2"),
        sa.Column("current_signature_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status",
                  sa.Enum("PENDING", "PARTIALLY_SIGNED", "FULLY_SIGNED", "WITHDRAWN",
                          name="seal_session_status"),
                  nullable=False, server_default="PENDING"),
        sa.Column("opinion_snapshot", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_seal_session_engagement", "seal_session", ["engagement_id"])

    # ── 5. Create seal_signature table ────────────────────────────────────────
    op.create_table(
        "seal_signature",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("seal_session_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("seal_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_user_id", sa.String(120), nullable=False),
        sa.Column("partner_email", sa.String(255), nullable=False),
        sa.Column("role",
                  sa.Enum("ENGAGEMENT_PARTNER", "EQCR_PARTNER", "COMPONENT_AUDITOR",
                          "JOINT_AUDITOR", "REGULATORY_COSIGN",
                          name="partner_role"),
                  nullable=False, server_default="ENGAGEMENT_PARTNER"),
        sa.Column("jurisdiction", sa.String(20), nullable=False, server_default="IN"),
        sa.Column("override_count_acknowledged", sa.Integer, nullable=False, server_default="0"),
        sa.Column("override_ack_confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("signature_hash", sa.String(64), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text, nullable=True),
        sa.UniqueConstraint("seal_session_id", "partner_user_id", name="uq_session_partner"),
    )
    op.create_index("ix_seal_signature_session", "seal_signature", ["seal_session_id"])

    # ── 6. Add context-lock columns to audit_opinion ──────────────────────────
    with op.batch_alter_table("audit_opinion") as batch_op:
        batch_op.add_column(sa.Column("opinion_hash",        sa.String(64),  nullable=True))
        batch_op.add_column(sa.Column("weight_set_version",  sa.Integer,     nullable=True))
        batch_op.add_column(sa.Column("rule_snapshot_hash",  sa.String(64),  nullable=True))
        batch_op.add_column(sa.Column("decision_hashes",     sa.JSON,        nullable=True, server_default="[]"))
        batch_op.add_column(sa.Column("exception_ids",       sa.JSON,        nullable=True, server_default="[]"))
        batch_op.add_column(sa.Column("materiality_amount",  sa.Float,       nullable=True))
        batch_op.add_column(sa.Column("system_version",      sa.String(32),  nullable=True))


def downgrade() -> None:
    # Remove context-lock columns
    with op.batch_alter_table("audit_opinion") as batch_op:
        batch_op.drop_column("opinion_hash")
        batch_op.drop_column("weight_set_version")
        batch_op.drop_column("rule_snapshot_hash")
        batch_op.drop_column("decision_hashes")
        batch_op.drop_column("exception_ids")
        batch_op.drop_column("materiality_amount")
        batch_op.drop_column("system_version")

    op.drop_index("ix_seal_signature_session", "seal_signature")
    op.drop_table("seal_signature")
    op.drop_index("ix_seal_session_engagement", "seal_session")
    op.drop_table("seal_session")

    # Note: PostgreSQL does not support DROP TYPE ... VALUE, so enum value removal
    # is NOT reversed here. SEALED stays in engagement_status after downgrade.
    # The seal_session_status and partner_role types are dropped:
    op.execute("DROP TYPE IF EXISTS seal_session_status")
    op.execute("DROP TYPE IF EXISTS partner_role")
