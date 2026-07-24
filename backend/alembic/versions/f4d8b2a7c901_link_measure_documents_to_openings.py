"""Link measure mission documents to individual openings.

Revision ID: f4d8b2a7c901
Revises: e9c7a4d2b613
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d8b2a7c901"
down_revision: Union[str, None] = "e9c7a4d2b613"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    columns = {column["name"] for column in _inspector().get_columns("measure_mission_documents")}
    indexes = {index["name"] for index in _inspector().get_indexes("measure_mission_documents")}
    if "opening_id" not in columns:
        with op.batch_alter_table("measure_mission_documents") as batch_op:
            batch_op.add_column(sa.Column("opening_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_measure_mission_documents_opening_id",
                "measure_openings",
                ["opening_id"],
                ["id"],
                ondelete="CASCADE",
            )
    if "ix_measure_mission_documents_opening_id" not in indexes:
        op.create_index(
            "ix_measure_mission_documents_opening_id",
            "measure_mission_documents",
            ["opening_id"],
            unique=False,
        )


def downgrade() -> None:
    columns = {column["name"] for column in _inspector().get_columns("measure_mission_documents")}
    indexes = {index["name"] for index in _inspector().get_indexes("measure_mission_documents")}
    if "opening_id" not in columns:
        return
    if "ix_measure_mission_documents_opening_id" in indexes:
        op.drop_index(
            "ix_measure_mission_documents_opening_id",
            table_name="measure_mission_documents",
        )
    with op.batch_alter_table("measure_mission_documents") as batch_op:
        batch_op.drop_constraint(
            "fk_measure_mission_documents_opening_id",
            type_="foreignkey",
        )
        batch_op.drop_column("opening_id")
