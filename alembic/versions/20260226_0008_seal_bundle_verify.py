# pyre-ignore-all-errors
"""
Alembic Migration: Seal Bundle Persistence & Verification Columns
=================================================================
Adds three columns to `engagement`:
  - seal_bundle       JSON — stores full WORM payload for replay verification
  - seal_key_version  VARCHAR(32) — HMAC key version used at seal time
  - seal_verify_status VARCHAR(16) — last verification result (VERIFIED/MISMATCH/PENDING)

Revision: 20260226_0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision      = "20260226_0008"
down_revision = "20260226_0007"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    with op.batch_alter_table("engagement") as batch_op:
        batch_op.add_column(sa.Column("seal_bundle",        sa.JSON,        nullable=True))
        batch_op.add_column(sa.Column("seal_key_version",   sa.String(32),  nullable=True))
        batch_op.add_column(sa.Column("seal_verify_status", sa.String(16),  nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("engagement") as batch_op:
        batch_op.drop_column("seal_bundle")
        batch_op.drop_column("seal_key_version")
        batch_op.drop_column("seal_verify_status")
