"""Expand planning licences and safety qualifications.

Revision ID: a3f6c9e2b715
Revises: f9c8b7a6d5e4
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "a3f6c9e2b715"
down_revision = "f9c8b7a6d5e4"
branch_labels = None
depends_on = None


QUALIFICATIONS = [
    {
        "code": "PERMIS_B",
        "name": "Permis B",
        "category": "LICENSE",
        "description": "Conduite des véhicules légers de l'entreprise.",
    },
    {
        "code": "PERMIS_BE",
        "name": "Permis BE",
        "category": "LICENSE",
        "description": "Conduite d'un véhicule léger avec remorque lourde.",
    },
    {
        "code": "CACES_R489",
        "name": "CACES R489 - Chariots",
        "category": "CERTIFICATION",
        "description": "Conduite en sécurité des chariots de manutention.",
    },
    {
        "code": "CACES_R486_NACELLE",
        "name": "CACES R486 - Nacelle",
        "category": "CERTIFICATION",
        "description": "Conduite d'une plateforme élévatrice mobile de personnel.",
    },
    {
        "code": "TRAVAIL_HAUTEUR",
        "name": "Travail en hauteur",
        "category": "CERTIFICATION",
        "description": "Formation et autorisation de travail en hauteur.",
    },
    {
        "code": "PORT_HARNAIS",
        "name": "Port du harnais",
        "category": "CERTIFICATION",
        "description": "Utilisation et contrôle des équipements antichute.",
    },
    {
        "code": "HABILITATION_ELECTRIQUE",
        "name": "Habilitation électrique",
        "category": "CERTIFICATION",
        "description": "Habilitation électrique adaptée aux interventions confiées.",
    },
    {
        "code": "SST",
        "name": "Sauveteur secouriste du travail",
        "category": "CERTIFICATION",
        "description": "Certificat SST en cours de validité.",
    },
]


def upgrade():
    skills = sa.table(
        "planning_skills",
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("requires_expiry", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )

    op.execute(
        skills.update()
        .where(skills.c.code == "PERMIS")
        .values(
            name="Permis générique (historique)",
            description="Compatibilité historique. Utiliser désormais un permis précis.",
            requires_expiry=False,
        )
    )
    op.execute(
        skills.update()
        .where(skills.c.code == "HABILITATION")
        .values(
            name="Habilitation générique (historique)",
            description="Compatibilité historique. Utiliser désormais une habilitation précise.",
            requires_expiry=False,
        )
    )

    connection = op.get_bind()
    existing_codes = set(
        connection.execute(
            sa.select(skills.c.code).where(
                skills.c.code.in_(
                    [qualification["code"] for qualification in QUALIFICATIONS]
                )
            )
        ).scalars()
    )
    missing = [
        {
            **qualification,
            "requires_expiry": True,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
        for qualification in QUALIFICATIONS
        if qualification["code"] not in existing_codes
    ]
    if missing:
        op.bulk_insert(skills, missing)


def downgrade():
    skills = sa.table(
        "planning_skills",
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("requires_expiry", sa.Boolean()),
    )
    op.execute(
        skills.delete().where(
            skills.c.code.in_(
                [qualification["code"] for qualification in QUALIFICATIONS]
            )
        )
    )
    op.execute(
        skills.update()
        .where(skills.c.code == "PERMIS")
        .values(
            name="Permis de conduire",
            description="Permis requis pour la ressource véhicule affectée.",
            requires_expiry=True,
        )
    )
    op.execute(
        skills.update()
        .where(skills.c.code == "HABILITATION")
        .values(
            name="Habilitation",
            description="Habilitation métier ou sécurité contrôlée.",
            requires_expiry=True,
        )
    )
