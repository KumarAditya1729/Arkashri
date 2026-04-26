"""Merge heads for audit operationalization

Revision ID: e2e03aa74569
Revises: 20260419_0012, 41c76a5410b9
Create Date: 2026-04-19 13:33:03.622248

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'e2e03aa74569'
down_revision: Union[str, None] = ('20260419_0012', '41c76a5410b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
