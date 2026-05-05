"""Add caption and poster metadata columns

Revision ID: 007
Revises: 006
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "renders",
        sa.Column("caption_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_format", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_sidecar_path", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_sidecar_media_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_sidecar_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_cue_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("caption_burned_in", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("poster_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("poster_timestamp_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("poster_media_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "renders",
        sa.Column("poster_filename", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("renders", "poster_filename")
    op.drop_column("renders", "poster_media_type")
    op.drop_column("renders", "poster_timestamp_seconds")
    op.drop_column("renders", "poster_mode")
    op.drop_column("renders", "caption_burned_in")
    op.drop_column("renders", "caption_cue_count")
    op.drop_column("renders", "caption_sidecar_filename")
    op.drop_column("renders", "caption_sidecar_media_type")
    op.drop_column("renders", "caption_sidecar_path")
    op.drop_column("renders", "caption_format")
    op.drop_column("renders", "caption_mode")
