"""Limitation de débit maison (sans dépendance externe) pour les endpoints sensibles.

Utilisé par ``POST /token`` : les opérateurs se connectent avec un PIN à
4 chiffres, la force brute serait triviale sans garde-fou.

Stratégie : compteur par couple (IP client, username) en fenêtre glissante.
Après ``max_failures`` échecs dans ``window_seconds`` secondes, le couple est
bloqué pendant ``block_seconds`` secondes (HTTP 429). Un succès remet le
compteur à zéro.

Thread-safety : ``threading.Lock`` (et non ``asyncio.Lock``) car les sections
critiques ne contiennent aucun ``await`` — de simples opérations dict O(1) —
et le verrou doit fonctionner quel que soit la boucle d'événements ou le
thread appelant (uvicorn, TestClient, tests unitaires).

LIMITATION CONNUE — déploiement multi-instance : le compteur est en mémoire
vive, donc **par processus**. C'est acceptable pour le déploiement cible
(mono-conteneur Docker, un seul processus uvicorn). Si le backend est un jour
répliqué derrière un load balancer, chaque instance aura son propre compteur
(la limite effective sera multipliée par le nombre de réplicas) : il faudra
alors externaliser l'état dans Redis (ex. ``INCR`` + ``EXPIRE`` sur une clé
``login_fail:{ip}:{username}``) ou utiliser un rate limiter au niveau du
reverse proxy (nginx ``limit_req``, Traefik, Cloudflare…).
"""

import os
import threading
import time
from collections import deque
from typing import Optional, Tuple


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class LoginRateLimiter:
    """Compteur d'échecs de connexion thread-safe, en mémoire."""

    def __init__(
        self,
        max_failures: Optional[int] = None,
        window_seconds: Optional[int] = None,
        block_seconds: Optional[int] = None,
    ):
        self.max_failures = max_failures or _env_int("LOGIN_RATE_LIMIT_MAX_FAILURES", 5)
        self.window_seconds = window_seconds or _env_int("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
        self.block_seconds = block_seconds or _env_int("LOGIN_RATE_LIMIT_BLOCK_SECONDS", 600)
        self._failures: dict = {}
        self._blocked_until: dict = {}
        self._lock = threading.Lock()

    def check_blocked(self, key: Tuple[str, str]) -> int:
        """Retourne le nombre de secondes de blocage restantes (0 si non bloqué)."""
        with self._lock:
            blocked_until = self._blocked_until.get(key, 0.0)
            remaining = blocked_until - time.monotonic()
            if remaining > 0:
                return int(remaining) + 1
            self._blocked_until.pop(key, None)
            return 0

    def record_failure(self, key: Tuple[str, str]) -> int:
        """Enregistre un échec. Retourne les secondes de blocage si le seuil est atteint, sinon 0."""
        now = time.monotonic()
        with self._lock:
            failures = self._failures.setdefault(key, deque())
            # Fenêtre glissante : on ne conserve que les échecs récents.
            while failures and now - failures[0] > self.window_seconds:
                failures.popleft()
            failures.append(now)
            if len(failures) >= self.max_failures:
                self._blocked_until[key] = now + self.block_seconds
                failures.clear()
                return self.block_seconds
            return 0

    def reset(self, key: Tuple[str, str]) -> None:
        """Remet le compteur à zéro (appelé après une connexion réussie)."""
        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def reset_all(self) -> None:
        """Vide tout l'état (utilisé par les tests)."""
        with self._lock:
            self._failures.clear()
            self._blocked_until.clear()


# Instance partagée, utilisée par le endpoint /token (backend/main.py).
login_rate_limiter = LoginRateLimiter()
