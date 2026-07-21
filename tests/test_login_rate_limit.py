"""Tests du rate limiting anti force brute sur POST /token.

PIN à 4 chiffres côté opérateurs : sans limitation, la force brute est
triviale. Le limiteur (backend/core/rate_limit.py) bloque par couple
(IP, username) après 5 échecs, pour 10 minutes, et se remet à zéro au succès.
"""

import sys
import time
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import models
from backend.core.rate_limit import LoginRateLimiter, login_rate_limiter
from backend.core.security import get_password_hash


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Le limiteur est un état module-level partagé : on le vide entre tests."""
    login_rate_limiter.reset_all()
    yield
    login_rate_limiter.reset_all()


@pytest.fixture()
def client(isolated_client):
    test_client, TestingSessionLocal = isolated_client
    with TestingSessionLocal() as db:
        db.add(
            models.User(
                username="operateur",
                pin_hash=get_password_hash("1234"),
                role="OPERATOR",
                is_active=True,
            )
        )
        db.commit()
    return test_client


def _failed_login(client) -> int:
    return client.post("/token", data={"username": "operateur", "password": "9999"}).status_code


def test_sixth_failed_attempt_is_blocked_with_429(client):
    # 5 premiers échecs : réponse métier normale (400)
    for _ in range(5):
        assert _failed_login(client) == 400

    # 6e tentative : blocage 429 avec message français et Retry-After
    response = client.post("/token", data={"username": "operateur", "password": "9999"})
    assert response.status_code == 429
    assert "tentatives" in response.json()["detail"].lower()
    assert int(response.headers["Retry-After"]) > 0

    # Le blocage vaut aussi pour le BON mot de passe tant qu'il est actif
    response = client.post("/token", data={"username": "operateur", "password": "1234"})
    assert response.status_code == 429


def test_successful_login_resets_failure_counter(client):
    # 4 échecs (sous le seuil de 5)
    for _ in range(4):
        assert _failed_login(client) == 400

    # Succès : le compteur est remis à zéro
    response = client.post("/token", data={"username": "operateur", "password": "1234"})
    assert response.status_code == 200, response.text

    # On peut à nouveau échouer 5 fois sans être bloqué (la 6e bloque)
    for _ in range(5):
        assert _failed_login(client) == 400
    assert _failed_login(client) == 429


def test_block_is_scoped_per_username(client):
    for _ in range(5):
        assert _failed_login(client) == 400
    assert _failed_login(client) == 429

    # Un autre username (même IP) n'est pas bloqué
    response = client.post("/token", data={"username": "autre", "password": "9999"})
    assert response.status_code == 400


def test_limiter_block_expires():
    """Test unitaire du limiteur : le blocage expire après block_seconds."""
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60, block_seconds=1)
    key = ("127.0.0.1", "user")

    assert limiter.record_failure(key) == 0
    assert limiter.record_failure(key) == 1  # seuil atteint -> blocage 1 s
    assert limiter.check_blocked(key) > 0
    time.sleep(1.1)
    assert limiter.check_blocked(key) == 0


def test_limiter_sliding_window():
    """Les échecs anciens (hors fenêtre) ne comptent plus."""
    limiter = LoginRateLimiter(max_failures=3, window_seconds=1, block_seconds=60)
    key = ("127.0.0.1", "user")

    assert limiter.record_failure(key) == 0
    assert limiter.record_failure(key) == 0
    time.sleep(1.1)  # les 2 échecs sortent de la fenêtre
    assert limiter.record_failure(key) == 0  # compteur reparti à 1
    assert limiter.check_blocked(key) == 0
