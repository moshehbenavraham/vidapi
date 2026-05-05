"""Add template_id and template_version_id to renders table

Revision ID: 004
Revises: 003
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "renders",
        sa.Column("template_id", sa.String(), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("template_version_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_renders_template_id",
        "renders",
        ["template_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_renders_template_id", table_name="renders")
    op.drop_column("renders", "template_version_id")
    op.drop_column("renders", "template_id")
