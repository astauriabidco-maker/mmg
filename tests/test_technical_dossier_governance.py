from types import SimpleNamespace

from backend.routers.v2_mmg import _records_from_technical_version
from backend.services.technical_dossier_governance import (
    build_document_matrix,
    compare_material_versions,
)


def _record(reference, quantity, *, supplier="CORTIZO", unit="barre", length_mm=6500):
    return {
        "supplier": supplier,
        "reference": reference,
        "designation": reference,
        "quantity": quantity,
        "unit": unit,
        "length_mm": length_mm,
    }


def test_compare_material_versions_reports_added_removed_and_quantity_changes():
    result = compare_material_versions(
        [_record("A", 2), _record("B", 4)],
        [_record("A", 5), _record("C", 1)],
    )

    assert result["has_changes"] is True
    assert result["added_count"] == 1
    assert result["removed_count"] == 1
    assert result["changed_count"] == 1
    assert result["quantity_delta"] == 0
    assert result["changed"][0]["reference"] == "A"
    assert result["changed"][0]["quantity_delta"] == 3


def test_compare_material_versions_aggregates_duplicate_lines():
    result = compare_material_versions(
        [_record("A", 2), _record("A", 3)],
        [_record("A", 5)],
    )

    assert result["has_changes"] is False
    assert result["changed"] == []


class _Version:
    def __init__(
        self,
        document_type,
        version_number,
        filename,
        status="DOCUMENT_ONLY",
        reference="AFF-42",
    ):
        self.document_type = document_type
        self.version_number = version_number
        self.original_filename = filename
        self.analysis_status = status
        self.source_system = "PROGES"
        self.detected_project_reference = reference
        self.source_reference = None


def test_document_matrix_requires_fabrication_and_cutting():
    incomplete = build_document_matrix([_Version("FABRICATION", 1, "atelier.pdf")])
    assert incomplete["complete"] is False
    assert incomplete["missing"] == ["CUTTING"]

    complete = build_document_matrix(
        [
            _Version("FABRICATION", 1, "atelier.pdf"),
            _Version("CUTTING", 2, "SEPVER.TXT", "PARSED"),
        ]
    )
    assert complete["complete"] is True
    assert complete["reference_consistent"] is True


def test_document_matrix_reference_consistency_uses_latest_versions_only():
    matrix = build_document_matrix(
        [
            _Version("FABRICATION", 1, "old-atelier.pdf", reference="OLD-001"),
            _Version("CUTTING", 2, "old-cutting.pdf", "PARSED", reference="OLD-001"),
            _Version("FABRICATION", 3, "atelier.pdf", "PARSED", reference="NEW-002"),
            _Version("CUTTING", 4, "cutting.pdf", "PARSED", reference="NEW-002"),
        ]
    )

    assert matrix["complete"] is True
    assert matrix["external_references"] == ["NEW-002"]
    assert matrix["reference_consistent"] is True


def test_legacy_parsed_records_are_normalized_for_stock_preview():
    version = SimpleNamespace(
        original_filename="ancienne-optimisation.pdf",
        parsed_records=[
            {
                "supplier": "CORTIZO",
                "reference": "202004",
                "designation": "Profil dormant",
                "quantity": 3,
                "unit": "barre",
            }
        ],
    )

    records = _records_from_technical_version(version)

    assert len(records) == 1
    assert records[0].source == "ancienne-optimisation.pdf"
    assert records[0].row is None
    assert records[0].reference == "202004"
