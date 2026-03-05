"""Add payer_configs table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payer_configs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("payer_id", sa.String(60), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payer_configs_payer_id", "payer_configs", ["payer_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payer_configs_payer_id", table_name="payer_configs")
    op.drop_table("payer_configs")
