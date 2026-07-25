"""Enrich technical document versions with parsing and stock approval metadata.

Revision ID: a9d4e7f2c631
Revises: a6c9d3e7f214
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d4e7f2c631"
down_revision: Union[str, None] = "a6c9d3e7f214"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    dossier_table = "technical_dossiers"
    dossier_columns = _columns(dossier_table)
    if dossier_columns:
        dossier_additions = (
            ("external_source_system", sa.String(), True, None),
            ("external_project_reference", sa.String(), True, None),
            ("stock_status", sa.String(), False, "LOCKED"),
            ("stock_review_note", sa.Text(), True, None),
            ("stock_validated_at", sa.DateTime(), True, None),
            ("stock_validated_by", sa.String(), True, None),
            ("launch_status", sa.String(), False, "LOCKED"),
            ("launch_review_note", sa.Text(), True, None),
            ("launch_validated_at", sa.DateTime(), True, None),
            ("launch_validated_by", sa.String(), True, None),
            ("launched_at", sa.DateTime(), True, None),
            ("launched_by", sa.String(), True, None),
        )
        with op.batch_alter_table(dossier_table) as batch:
            for name, column_type, nullable, default in dossier_additions:
                if name not in dossier_columns:
                    batch.add_column(
                        sa.Column(
                            name,
                            column_type,
                            nullable=nullable,
                            server_default=default,
                        )
                    )
        dossier_indexes = {
            index["name"]
            for index in sa.inspect(op.get_bind()).get_indexes(dossier_table)
        }
        for name in (
            "external_source_system",
            "external_project_reference",
            "stock_status",
            "launch_status",
        ):
            index_name = f"ix_technical_dossiers_{name}"
            if index_name not in dossier_indexes:
                op.create_index(index_name, dossier_table, [name])
        op.execute(
            sa.text(
                """
                UPDATE technical_dossiers
                SET stock_status = 'TO_REVIEW'
                WHERE production_status = 'VALIDATED'
                  AND stock_status = 'LOCKED'
                """
            )
        )

    table = "technical_dossier_versions"
    columns = _columns(table)
    if not columns:
        return

    additions = (
        ("analysis_status", sa.String(), False, "PENDING"),
        ("detected_document_type", sa.String(), True, None),
        ("detected_source_system", sa.String(), True, None),
        ("detected_project_reference", sa.String(), True, None),
        ("parsed_summary", sa.JSON(), False, "{}"),
        ("parsed_records", sa.JSON(), False, "[]"),
        ("parsed_issues", sa.JSON(), False, "[]"),
        ("analyzed_at", sa.DateTime(), True, None),
        ("stock_data_approved_at", sa.DateTime(), True, None),
        ("stock_data_approved_by", sa.String(), True, None),
        ("previous_version_id", sa.Integer(), True, None),
        ("comparison_summary", sa.JSON(), False, "{}"),
        ("impact_status", sa.String(), False, "INITIAL"),
        ("revision_after_launch", sa.Boolean(), False, "false"),
        ("revision_status", sa.String(), False, "NOT_REQUIRED"),
        ("revision_review_note", sa.Text(), True, None),
        ("revision_reviewed_at", sa.DateTime(), True, None),
        ("revision_reviewed_by", sa.String(), True, None),
    )
    with op.batch_alter_table(table) as batch:
        for name, column_type, nullable, default in additions:
            if name not in columns:
                batch.add_column(
                    sa.Column(
                        name,
                        column_type,
                        nullable=nullable,
                        server_default=default,
                    )
                )
    foreign_keys = {
        constraint.get("name")
        for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table)
    }
    if "fk_technical_versions_previous_version" not in foreign_keys:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                "fk_technical_versions_previous_version",
                table,
                ["previous_version_id"],
                ["id"],
                ondelete="SET NULL",
            )

    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes(table)}
    if "ix_technical_dossier_versions_analysis_status" not in indexes:
        op.create_index(
            "ix_technical_dossier_versions_analysis_status",
            table,
            ["analysis_status"],
        )
    if "ix_technical_dossier_versions_detected_project_reference" not in indexes:
        op.create_index(
            "ix_technical_dossier_versions_detected_project_reference",
            table,
            ["detected_project_reference"],
        )
    for name in ("previous_version_id", "impact_status", "revision_status"):
        index_name = f"ix_technical_dossier_versions_{name}"
        if index_name not in indexes:
            op.create_index(index_name, table, [name])


def downgrade() -> None:
    table = "technical_dossier_versions"
    columns = _columns(table)
    if not columns:
        return
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes(table)}
    for index_name in (
        "ix_technical_dossier_versions_revision_status",
        "ix_technical_dossier_versions_impact_status",
        "ix_technical_dossier_versions_previous_version_id",
        "ix_technical_dossier_versions_detected_project_reference",
        "ix_technical_dossier_versions_analysis_status",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
    with op.batch_alter_table(table) as batch:
        foreign_keys = {
            constraint.get("name")
            for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table)
        }
        if "fk_technical_versions_previous_version" in foreign_keys:
            batch.drop_constraint(
                "fk_technical_versions_previous_version",
                type_="foreignkey",
            )
        for name in (
            "revision_reviewed_by",
            "revision_reviewed_at",
            "revision_review_note",
            "revision_status",
            "revision_after_launch",
            "impact_status",
            "comparison_summary",
            "previous_version_id",
            "stock_data_approved_by",
            "stock_data_approved_at",
            "analyzed_at",
            "parsed_issues",
            "parsed_records",
            "parsed_summary",
            "detected_project_reference",
            "detected_source_system",
            "detected_document_type",
            "analysis_status",
        ):
            if name in columns:
                batch.drop_column(name)

    dossier_table = "technical_dossiers"
    dossier_columns = _columns(dossier_table)
    if dossier_columns:
        dossier_indexes = {
            index["name"]
            for index in sa.inspect(op.get_bind()).get_indexes(dossier_table)
        }
        for name in (
            "launch_status",
            "stock_status",
            "external_project_reference",
            "external_source_system",
        ):
            index_name = f"ix_technical_dossiers_{name}"
            if index_name in dossier_indexes:
                op.drop_index(index_name, table_name=dossier_table)
        with op.batch_alter_table(dossier_table) as batch:
            for name in (
                "launched_by",
                "launched_at",
                "launch_validated_by",
                "launch_validated_at",
                "launch_review_note",
                "launch_status",
                "stock_validated_by",
                "stock_validated_at",
                "stock_review_note",
                "stock_status",
                "external_project_reference",
                "external_source_system",
            ):
                if name in dossier_columns:
                    batch.drop_column(name)
