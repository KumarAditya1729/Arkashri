# pyre-ignore-all-errors
"""regulatory scheduler and alert tables

Revision ID: 20260224_0006
Revises: 20260224_0005
Create Date: 2026-02-24 02:25:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260224_0006"
down_revision: Union[str, None] = "20260224_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schedule_cadence_enum = postgresql.ENUM(
    "HOURLY",
    "DAILY",
    name="schedule_cadence",
    create_type=False,
)
schedule_state_enum = postgresql.ENUM(
    "IDLE",
    "SUCCESS",
    "RETRY",
    "FAILED",
    name="schedule_state",
    create_type=False,
)
alert_severity_enum = postgresql.ENUM(
    "INFO",
    "WARNING",
    "CRITICAL",
    name="alert_severity",
    create_type=False,
)
alert_type_enum = postgresql.ENUM(
    "SYNC_FAILURE",
    "SYNC_RECOVERY",
    name="alert_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    schedule_cadence_enum.create(bind, checkfirst=True)
    schedule_state_enum.create(bind, checkfirst=True)
    alert_severity_enum.create(bind, checkfirst=True)
    alert_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "regulatory_sync_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("cadence", schedule_cadence_enum, nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("daily_hour", sa.Integer(), nullable=True),
        sa.Column("daily_minute", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("backoff_base_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", schedule_state_enum, nullable=False, server_default="IDLE"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["source_id"], ["regulatory_source.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", name="uq_regulatory_schedule_source"),
    )

    op.create_table(
        "regulatory_sync_alert",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=True),
        sa.Column("ingest_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("severity", alert_severity_enum, nullable=False),
        sa.Column("alert_type", alert_type_enum, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["regulatory_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["regulatory_sync_schedule.id"]),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["regulatory_ingest_run.id"]),
    )

    op.create_index(
        "ix_regulatory_schedule_next_run",
        "regulatory_sync_schedule",
        ["is_active", "next_run_at"],
    )
    op.create_index(
        "ix_regulatory_alert_scope_created",
        "regulatory_sync_alert",
        ["source_id", "created_at"],
    )
    op.create_index(
        "ix_regulatory_alert_ack",
        "regulatory_sync_alert",
        ["is_acknowledged", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_regulatory_alert_ack", table_name="regulatory_sync_alert")
    op.drop_index("ix_regulatory_alert_scope_created", table_name="regulatory_sync_alert")
    op.drop_index("ix_regulatory_schedule_next_run", table_name="regulatory_sync_schedule")

    op.drop_table("regulatory_sync_alert")
    op.drop_table("regulatory_sync_schedule")

    bind = op.get_bind()
    alert_type_enum.drop(bind, checkfirst=True)
    alert_severity_enum.drop(bind, checkfirst=True)
    schedule_state_enum.drop(bind, checkfirst=True)
    schedule_cadence_enum.drop(bind, checkfirst=True)
