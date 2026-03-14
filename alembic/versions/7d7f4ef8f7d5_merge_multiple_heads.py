# pyre-ignore-all-errors
"""merge_multiple_heads

Revision ID: 7d7f4ef8f7d5
Revises: 20260228_0010, 73aee8dd1554
Create Date: 2026-03-08 01:08:23.235497

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '7d7f4ef8f7d5'
down_revision: Union[str, None] = ('20260228_0010', '73aee8dd1554')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
