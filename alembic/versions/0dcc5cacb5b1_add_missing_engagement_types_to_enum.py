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
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction block
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("COMMIT")
    
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
        if connection.dialect.name == "postgresql":
            # The type must be modified outside of an active transaction
            op.execute(f"ALTER TYPE engagement_type ADD VALUE IF NOT EXISTS '{eng_type}'")

def downgrade() -> None:
    pass
