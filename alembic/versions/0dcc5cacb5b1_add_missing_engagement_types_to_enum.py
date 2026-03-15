"""add missing engagement types to enum

Revision ID: 0dcc5cacb5b1
Revises: 42b05e8f9d7e
Create Date: 2026-03-15 12:22:53.463936

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dcc5cacb5b1'
down_revision: Union[str, None] = '42b05e8f9d7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add newly introduced Enum values to Postgres ENUM type
    new_types = [
        'FINANCIAL_AUDIT',
        'EXTERNAL_AUDIT',
        'COMPLIANCE_AUDIT',
        'OPERATIONAL_AUDIT',
        'TAX_AUDIT',
        'PERFORMANCE_AUDIT',
        'ENVIRONMENTAL_AUDIT',
        'PAYROLL_AUDIT',
        'QUALITY_AUDIT',
        'SINGLE_AUDIT'
    ]
    for eng_type in new_types:
        op.execute(f"ALTER TYPE engagement_type ADD VALUE IF NOT EXISTS '{eng_type}'")


def downgrade() -> None:
    # Removing ENUM values is not natively supported in Postgres without recreating the type
    pass
