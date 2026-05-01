# pyre-ignore-all-errors
"""reconcile engagement schema with production model

Revision ID: 20260430_0014
Revises: 20260427_0013
Create Date: 2026-04-30 07:45:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.compiler import IdentifierPreparer


revision = "20260430_0014"
down_revision = "20260427_0013"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    preparer = IdentifierPreparer(bind.dialect)
    quoted_type_name = preparer.quote(type_name)
    literal_processor = sa.String().literal_processor(bind.dialect)

    context = op.get_context()
    with context.autocommit_block():
        for value in values:
            # PostgreSQL does not support bind parameters in ALTER TYPE ADD VALUE.
            # Quote the enum label with the dialect literal processor instead.
            enum_label = literal_processor(value) if literal_processor else repr(value)
            op.execute(sa.text(f"ALTER TYPE {quoted_type_name} ADD VALUE IF NOT EXISTS {enum_label}"))


def upgrade() -> None:
    # Older databases were created before the current Engagement model gained
    # these nullable fields. Add only missing columns so the migration is safe
    # for both fresh and already-patched staging databases.
    existing_columns = _column_names("engagement")

    if "period_start" not in existing_columns:
        op.add_column("engagement", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    if "period_end" not in existing_columns:
        op.add_column("engagement", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))
    if "state_metadata" not in existing_columns:
        op.add_column("engagement", sa.Column("state_metadata", sa.JSON(), nullable=True))

    _add_enum_values(
        "engagement_type",
        (
            "INVENTORY_AUDIT",
            "COST_AUDIT",
            "SOCIAL_AUDIT",
        ),
    )
    _add_enum_values(
        "engagement_status",
        (
            "COLLECTED",
            "VERIFIED",
            "FLAGGED",
            "REVIEWED",
        ),
    )


def downgrade() -> None:
    existing_columns = _column_names("engagement")
    for column_name in ("state_metadata", "period_end", "period_start"):
        if column_name in existing_columns:
            op.drop_column("engagement", column_name)

    # PostgreSQL enum values are intentionally not removed on downgrade.
