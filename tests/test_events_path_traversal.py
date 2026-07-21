"""Tests anti path traversal sur la création des dossiers de production.

backend/core/events.py utilisait `client_name` tel quel pour nommer un
dossier : un nom comme "../../etc" aurait créé un dossier hors de
uploads/production_files. La whitelist de `sanitize_client_name` élimine
tout caractère dangereux et le chemin résolu est revérifié avec
Path.is_relative_to.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core.events import EventBus, sanitize_client_name


def test_sanitize_removes_traversal_sequences():
    assert ".." not in sanitize_client_name("../../etc")
    assert "/" not in sanitize_client_name("../../etc")
    assert sanitize_client_name("../../etc") == "etc"
    assert sanitize_client_name("..\\..\\windows") == "windows"
    assert sanitize_client_name("....//....//secret") == "secret"


def test_sanitize_keeps_legitimate_names():
    assert sanitize_client_name("SARL Dupont-Menuiserie") == "SARL Dupont-Menuiserie"
    assert sanitize_client_name("Client 42") == "Client 42"


def test_sanitize_replaces_special_characters():
    assert sanitize_client_name("M. O'Neil (fils) & Cie") == "M_ O_Neil _fils_ _ Cie"
    # Caractères accentués : remplacés (whitelist ASCII stricte, volontaire)
    assert sanitize_client_name("Éléonore") == "l_onore"


def test_sanitize_bounds_length_and_empty():
    assert len(sanitize_client_name("A" * 500)) == 50
    assert sanitize_client_name("") == "client-inconnu"
    assert sanitize_client_name("...") == "client-inconnu"
    assert sanitize_client_name(None) == "client-inconnu"


def test_production_folder_stays_inside_base_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    EventBus._task_create_production_folder(quote_id=7, client_name="../../etc")

    base = (tmp_path / "uploads" / "production_files").resolve()
    created = list(base.iterdir())
    assert len(created) == 1
    folder = created[0].resolve()
    # Le dossier créé est sain : nom sans traversal, bien dans le dossier parent
    assert ".." not in folder.name
    assert folder.name.endswith("_etc_CMD7")
    assert folder.is_relative_to(base)
    # Aucun dossier parasite créé en dehors de la base
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path / "uploads" / "etc").exists()


def test_production_folder_with_normal_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    EventBus._task_create_production_folder(quote_id=12, client_name="SARL Dupont")

    base = tmp_path / "uploads" / "production_files"
    folder = next(base.iterdir())
    assert folder.name.endswith("_SARL_Dupont_CMD12")
    assert folder.is_dir()
