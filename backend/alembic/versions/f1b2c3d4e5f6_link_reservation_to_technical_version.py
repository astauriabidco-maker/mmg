"""Link one stock reservation to one validated technical version.

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.add_column(
            sa.Column("technical_dossier_version_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_stock_reservation_technical_version",
            "technical_dossier_versions",
            ["technical_dossier_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_stock_reservations_technical_dossier_version_id",
            ["technical_dossier_version_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_reservations") as batch_op:
        batch_op.drop_index(
            "ix_stock_reservations_technical_dossier_version_id"
        )
        batch_op.drop_constraint(
            "fk_stock_reservation_technical_version",
            type_="foreignkey",
        )
        batch_op.drop_column("technical_dossier_version_id")
