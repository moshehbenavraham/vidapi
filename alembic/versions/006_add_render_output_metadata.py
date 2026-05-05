"""Add render output metadata columns

Revision ID: 006
Revises: 005
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "renders",
        sa.Column("output_format", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("output_media_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("output_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("output_frame_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("output_manifest_path", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("renders", "output_manifest_path")
    op.drop_column("renders", "output_frame_count")
    op.drop_column("renders", "output_filename")
    op.drop_column("renders", "output_media_type")
    op.drop_column("renders", "output_format")
