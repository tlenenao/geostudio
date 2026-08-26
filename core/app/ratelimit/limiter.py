# SPDX-License-Identifier: Apache-2.0
"""Rate limiting en mémoire process, par (clé d'appelant, groupe de route)
— design SP-26 §3.4. Clé d'appelant = l'en-tête Authorization brut, pas un
user_id résolu : ce middleware tourne AVANT l'injection de dépendances
FastAPI (donc avant get_current_user), et /mcp est un mount ASGI brut sans
dépendances du tout — décoder/vérifier le JWT ici dupliquerait toute la
logique de app.auth.dependency pour un usage qui n'a besoin que d'une clé
stable, pas d'une identité vérifiée. Limite assumée : ne tient pas
multi-process (pas de --workers aujourd'hui côté uvicorn, cf. C2/vague 0)."""

import re
import time
from collections import defaultdict, deque

_SQL_RE = re.compile(r"^/analytics/sql$")
_LLM_RE = re.compile(r"^/mcp$|^/copilot/turn$")
_HARVEST_RE = re.compile(r"^/harvest/")

# Budgets par groupe de coût réel (requêtes / 60s). Réutilise _EXPORT_PATH_RE
# de app.main pour le groupe "jobs" plutôt que de le redéfinir ici.
_BUDGETS = {
    "sql": 10,
    "llm": 20,
    "jobs": 15,
    "harvest": 10,
}
_WINDOW_SECONDS = 60.0


def route_group(path: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if _HARVEST_RE.match(path):
        return "harvest"
    return None


class RateLimiter:
    """Compteur glissant par (clé, groupe) — deque d'horodatages, purgée à
    chaque appel. Pas de nettoyage périodique en arrière-plan : une clé
    inactive garde une deque vide en mémoire indéfiniment, coût négligeable
    face au volume de callers distincts attendu (limite documentée, pas un
    bug — cf. design §7)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, key: str, group: str) -> bool:
        budget = _BUDGETS[group]
        now = time.monotonic()
        bucket = self._hits[(key, group)]
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= budget:
            return False
        bucket.append(now)
        return True
