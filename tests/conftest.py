"""Configuration pytest : isolation totale de la base de données en test.

Deux filets de sécurité, pour qu'AUCUN test ne dépende de ./atelier.db :

1. À l'import de ce module (exécuté par pytest AVANT tout import de
   `backend`), DATABASE_URL est redirigée vers un fichier SQLite temporaire.
   Tout code qui utiliserait encore le moteur par défaut (lifespan, seeds,
   endpoints qui court-circuitent l'injection de dépendances) tape alors une
   base jetable au lieu de la base de développement.
2. La fixture `isolated_client` fournit un TestClient dont TOUTES les routes
   testées utilisent une base SQLite en mémoire propre :
   - `get_db` est surchargé via `app.dependency_overrides` ;
   - `database.SessionLocal` est patché car le endpoint WebSocket
     (/ws/{client_id}) instancie sa session directement, sans Depends ;
   - le TestClient est utilisé en context manager pour que le lifespan
     (create_all + seeds, sur la base temporaire) s'exécute.
"""

import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="mmg-test-db-")
_ORIGINAL_DATABASE_URL = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TEST_DB_DIR, 'test.db')}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend import database, models  # noqa: E402
from backend.main import app  # noqa: E402

# Importe les modules de seed AVANT tout monkeypatch de database.SessionLocal.
# Ils font `from backend.database import SessionLocal` (liaison figée au moment
# de l'import) : en les important ici, cette liaison cible la base temporaire,
# sinon elle capturerait la session patchée d'une fixture (base morte après
# teardown) et les seeds du lifespan planteraient dans les tests suivants.
from backend import seed_permissions, seed_stations  # noqa: E402, F401

# La redirection ne devait valoir que pour la création du moteur
# `backend.database` (à l'import, ci-dessus). On restaure l'environnement pour
# ne pas perturber les tests qui pilotent Alembic : backend/alembic/env.py
# donne la priorité à DATABASE_URL sur l'URL passée à la Config.
if _ORIGINAL_DATABASE_URL is None:
    del os.environ["DATABASE_URL"]
else:
    os.environ["DATABASE_URL"] = _ORIGINAL_DATABASE_URL


@pytest.fixture()
def isolated_client(monkeypatch):
    """TestClient entièrement isolé de ./atelier.db.

    Yield (test_client, TestingSessionLocal) : la session factory permet
    d'alimenter ou d'inspecter la base en mémoire dans le test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db
    # Le endpoint WebSocket n'utilise pas Depends(get_db) : il appelle
    # database.SessionLocal() directement (résolution à l'appel -> patch OK).
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    try:
        with TestClient(app) as test_client:
            yield test_client, TestingSessionLocal
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)
