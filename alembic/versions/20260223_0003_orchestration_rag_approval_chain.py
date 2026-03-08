"""orchestration, approvals, rag, and chain attestations

Revision ID: 20260223_0003
Revises: 20260223_0002
Create Date: 2026-02-23 23:59:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260223_0003"
down_revision: Union[str, None] = "20260223_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

audit_run_status_enum = postgresql.ENUM(
    "DRAFT",
    "READY",
    "RUNNING",
    "BLOCKED",
    "COMPLETED",
    "FAILED",
    name="audit_run_status",
    create_type=False,
)
audit_step_status_enum = postgresql.ENUM(
    "PENDING",
    "IN_PROGRESS",
    "WAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    name="audit_step_status",
    create_type=False,
)
approval_status_enum = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    "ESCALATED",
    name="approval_status",
    create_type=False,
)
approval_action_type_enum = postgresql.ENUM(
    "SUBMITTED",
    "APPROVED",
    "REJECTED",
    "ESCALATED",
    "COMMENTED",
    name="approval_action_type",
    create_type=False,
)
knowledge_source_type_enum = postgresql.ENUM(
    "LAW",
    "STANDARD",
    "POLICY",
    "INTERNAL_NOTE",
    name="knowledge_source_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    audit_run_status_enum.create(bind, checkfirst=True)
    audit_step_status_enum.create(bind, checkfirst=True)
    approval_status_enum.create(bind, checkfirst=True)
    approval_action_type_enum.create(bind, checkfirst=True)
    knowledge_source_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "audit_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("audit_type", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_version", sa.String(length=32), nullable=False),
        sa.Column("status", audit_run_status_enum, nullable=False, server_default="DRAFT"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("run_hash", sa.String(length=64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_hash", name="uq_audit_run_hash"),
    )

    op.create_table(
        "audit_run_step",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.String(length=64), nullable=False),
        sa.Column("phase_name", sa.String(length=128), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("owner_role", sa.String(length=128), nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", audit_step_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("output_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("evidence_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["audit_run.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "phase_id", "step_id", name="uq_audit_run_step_key"),
    )

    op.create_table(
        "approval_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=False),
        sa.Column("reference_id", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("current_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", approval_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["step_id"], ["audit_run_step.id"]),
    )

    op.create_table(
        "approval_action",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", approval_action_type_enum, nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("action_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["approval_request.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_key", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("source_type", knowledge_source_type_enum, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_key", "jurisdiction", "version", name="uq_knowledge_document_version"),
    )

    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_hash", sa.String(length=64), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_document.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_index"),
    )

    op.create_table(
        "rag_query_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("audit_type", sa.String(length=64), nullable=True),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "chain_attestation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_anchor_id", sa.Integer(), nullable=False),
        sa.Column("adapter_key", sa.String(length=100), nullable=False),
        sa.Column("network", sa.String(length=100), nullable=False),
        sa.Column("tx_reference", sa.String(length=255), nullable=False),
        sa.Column("attestation_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["chain_anchor_id"], ["chain_anchor.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_audit_run_tenant_jurisdiction_created",
        "audit_run",
        ["tenant_id", "jurisdiction", "created_at"],
    )
    op.create_index("ix_audit_run_step_run_sequence", "audit_run_step", ["run_id", "sequence_no"])
    op.create_index(
        "ix_approval_request_tenant_jurisdiction_status",
        "approval_request",
        ["tenant_id", "jurisdiction", "status"],
    )
    op.create_index(
        "ix_knowledge_document_jurisdiction_source",
        "knowledge_document",
        ["jurisdiction", "source_type", "created_at"],
    )
    op.create_index("ix_knowledge_chunk_document_chunk", "knowledge_chunk", ["document_id", "chunk_index"])
    op.create_index(
        "ix_rag_query_log_tenant_jurisdiction_created",
        "rag_query_log",
        ["tenant_id", "jurisdiction", "created_at"],
    )
    op.create_index("ix_chain_attestation_anchor_id", "chain_attestation", ["chain_anchor_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_chain_attestation_anchor_id", table_name="chain_attestation")
    op.drop_index("ix_rag_query_log_tenant_jurisdiction_created", table_name="rag_query_log")
    op.drop_index("ix_knowledge_chunk_document_chunk", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_document_jurisdiction_source", table_name="knowledge_document")
    op.drop_index("ix_approval_request_tenant_jurisdiction_status", table_name="approval_request")
    op.drop_index("ix_audit_run_step_run_sequence", table_name="audit_run_step")
    op.drop_index("ix_audit_run_tenant_jurisdiction_created", table_name="audit_run")

    op.drop_table("chain_attestation")
    op.drop_table("rag_query_log")
    op.drop_table("knowledge_chunk")
    op.drop_table("knowledge_document")
    op.drop_table("approval_action")
    op.drop_table("approval_request")
    op.drop_table("audit_run_step")
    op.drop_table("audit_run")

    bind = op.get_bind()
    knowledge_source_type_enum.drop(bind, checkfirst=True)
    approval_action_type_enum.drop(bind, checkfirst=True)
    approval_status_enum.drop(bind, checkfirst=True)
    audit_step_status_enum.drop(bind, checkfirst=True)
    audit_run_status_enum.drop(bind, checkfirst=True)
