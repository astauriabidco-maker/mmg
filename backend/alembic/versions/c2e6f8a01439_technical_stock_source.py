"""Persist the technical dossier stock source.

Revision ID: c2e6f8a01439
Revises: b4e7d9c2a801
"""
from alembic import op
import sqlalchemy as sa

revision = "c2e6f8a01439"
down_revision = "b4e7d9c2a801"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("technical_dossiers") as batch:
        batch.add_column(sa.Column("stock_source_location_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_technical_stock_source", "stock_locations", ["stock_source_location_id"], ["id"])


def downgrade():
    with op.batch_alter_table("technical_dossiers") as batch:
        batch.drop_constraint("fk_technical_stock_source", type_="foreignkey")
        batch.drop_column("stock_source_location_id")
