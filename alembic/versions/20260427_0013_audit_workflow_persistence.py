# pyre-ignore-all-errors
"""add audit workflow persistence fields

Revision ID: 20260427_0013
Revises: e2e03aa74569
Create Date: 2026-04-27 16:10:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260427_0013"
down_revision = "e2e03aa74569"
branch_labels = None
depends_on = None


audit_workflow_type = sa.Enum(
    "statutory_audit",
    "tax_audit",
    "gst_audit",
    "internal_audit",
    "stock_audit",
    "bank_loan_audit",
    name="audit_workflow_type",
)

audit_sla_status = sa.Enum(
    "on_track",
    "at_risk",
    "delayed",
    "completed",
    name="audit_sla_status",
)

workflow_review_status = sa.Enum(
    "pending",
    "in_review",
    "changes_requested",
    "approved",
    name="workflow_review_status",
)

workflow_report_status = sa.Enum(
    "not_started",
    "draft",
    "ready_for_review",
    "generated",
    "sealed",
    name="workflow_report_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        audit_workflow_type.create(bind, checkfirst=True)
        audit_sla_status.create(bind, checkfirst=True)
        workflow_review_status.create(bind, checkfirst=True)
        workflow_report_status.create(bind, checkfirst=True)

    op.add_column("engagement", sa.Column("audit_type", audit_workflow_type, nullable=True))
    op.add_column("engagement", sa.Column("target_completion_days", sa.Integer(), nullable=True))
    op.add_column("engagement", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("engagement", sa.Column("due_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("engagement", sa.Column("current_day", sa.Integer(), nullable=True))
    op.add_column("engagement", sa.Column("sla_status", audit_sla_status, nullable=True))
    op.add_column("engagement", sa.Column("checklist_progress", sa.JSON(), nullable=True))
    op.add_column("engagement", sa.Column("document_progress", sa.JSON(), nullable=True))
    op.add_column("engagement", sa.Column("review_status", workflow_review_status, nullable=True))
    op.add_column("engagement", sa.Column("report_status", workflow_report_status, nullable=True))

    if is_postgres:
        op.execute(
            """
            UPDATE engagement
            SET
                audit_type = CASE engagement_type::text
                    WHEN 'TAX_AUDIT' THEN 'tax_audit'::audit_workflow_type
                    WHEN 'COMPLIANCE_AUDIT' THEN 'gst_audit'::audit_workflow_type
                    WHEN 'INTERNAL_AUDIT' THEN 'internal_audit'::audit_workflow_type
                    WHEN 'INVENTORY_AUDIT' THEN 'stock_audit'::audit_workflow_type
                    WHEN 'FINANCIAL_AUDIT' THEN 'bank_loan_audit'::audit_workflow_type
                    ELSE 'statutory_audit'::audit_workflow_type
                END,
                target_completion_days = 7,
                start_date = COALESCE(created_at, now()),
                due_date = COALESCE(created_at, now()) + interval '7 days',
                current_day = LEAST(7, GREATEST(1, (CURRENT_DATE - COALESCE(created_at, now())::date) + 1)),
                sla_status = CASE
                    WHEN status::text IN ('COMPLETED', 'SEALED') THEN 'completed'::audit_sla_status
                    WHEN now() > COALESCE(created_at, now()) + interval '7 days' THEN 'delayed'::audit_sla_status
                    ELSE 'on_track'::audit_sla_status
                END,
                checklist_progress = COALESCE(checklist_progress, '{}'::json),
                document_progress = COALESCE(document_progress, '{}'::json),
                review_status = 'pending'::workflow_review_status,
                report_status = CASE
                    WHEN status::text = 'SEALED' THEN 'sealed'::workflow_report_status
                    WHEN status::text = 'COMPLETED' THEN 'generated'::workflow_report_status
                    ELSE 'not_started'::workflow_report_status
                END
            WHERE audit_type IS NULL
            """
        )
    else:
        op.execute(
            """
            UPDATE engagement
            SET
                audit_type = 'statutory_audit',
                target_completion_days = 7,
                start_date = COALESCE(created_at, CURRENT_TIMESTAMP),
                due_date = datetime(COALESCE(created_at, CURRENT_TIMESTAMP), '+7 days'),
                current_day = 1,
                sla_status = 'on_track',
                checklist_progress = '{}',
                document_progress = '{}',
                review_status = 'pending',
                report_status = 'not_started'
            WHERE audit_type IS NULL
            """
        )

    for column_name in (
        "audit_type",
        "target_completion_days",
        "start_date",
        "due_date",
        "current_day",
        "sla_status",
        "checklist_progress",
        "document_progress",
        "review_status",
        "report_status",
    ):
        op.alter_column("engagement", column_name, nullable=False)


def downgrade() -> None:
    for column_name in (
        "report_status",
        "review_status",
        "document_progress",
        "checklist_progress",
        "sla_status",
        "current_day",
        "due_date",
        "start_date",
        "target_completion_days",
        "audit_type",
    ):
        op.drop_column("engagement", column_name)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        workflow_report_status.drop(bind, checkfirst=True)
        workflow_review_status.drop(bind, checkfirst=True)
        audit_sla_status.drop(bind, checkfirst=True)
        audit_workflow_type.drop(bind, checkfirst=True)
