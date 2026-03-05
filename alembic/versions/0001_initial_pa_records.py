"""Create pa_records table.

Revision ID: 0001
Revises: 
Create Date: 2026-03-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pa_records",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("pa_number", sa.String(30), nullable=False),
        sa.Column("patient_id", sa.String(60), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("cpt_codes", sa.JSON(), nullable=False),
        sa.Column("icd10_codes", sa.JSON(), nullable=False),
        sa.Column("turnaround_minutes", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_pa_records_pa_number", "pa_records", ["pa_number"], unique=True)
    op.create_index("ix_pa_records_patient_id", "pa_records", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_pa_records_patient_id", table_name="pa_records")
    op.drop_index("ix_pa_records_pa_number", table_name="pa_records")
    op.drop_table("pa_records")
