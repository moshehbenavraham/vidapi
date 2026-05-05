"""Add render output duration column

Revision ID: 008
Revises: 007
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "renders",
        sa.Column("output_duration_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("renders", "output_duration_seconds")
