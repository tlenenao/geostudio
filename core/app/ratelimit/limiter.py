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
# Ne couvre QUE les routes /harvest/* à coût réel (écriture, ou déclenchement
# d'un job de moissonnage externe) — trouvé en revue finale SP-26 (I1) :
# couvrir tout /harvest/* incluait GET /harvest/layers et
# GET /harvest/feature-layers, deux lectures pures (déjà enregistrées en
# base, aucun appel externe) que shell/src/map/LayerPicker.tsx interroge à
# CHAQUE frappe sans debounce — une recherche de 11 caractères épuisait le
# budget en quelques secondes, et Promise.allSettled côté shell avale le 429
# en silence (les couches externes disparaissent du sélecteur sans erreur
# visible). Les 4 routes de lecture (list_sources, list_layers,
# list_feature_layers, get_source) sont toutes des GET ; les 4 routes à coût
# réel (create/patch/delete/run) sont toutes des POST/PATCH/DELETE — la
# distinction se fait donc par méthode, pas seulement par chemin.
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


def route_group(path: str, method: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if _HARVEST_RE.match(path) and method != "GET":
        return "harvest"
    return None


# Périodicité du balayage complet (I4) : un passage sur tout `_hits` toutes
# les `_SWEEP_INTERVAL` requêtes, pas à chaque appel — un balayage complet
# à chaque requête serait O(nombre de clés distinctes vues récemment) sur
# le chemin chaud de CHAQUE requête HTTP, alors qu'un balayage occasionnel
# suffit à borner la croissance (les entrées périmées s'accumulent entre
# deux balayages, mais ne survivent jamais indéfiniment).
_SWEEP_INTERVAL = 50


class RateLimiter:
    """Compteur glissant par (clé, groupe) — deque d'horodatages, purgée à
    chaque appel pour la clé courante. Un balayage périodique (toutes les
    `_SWEEP_INTERVAL` requêtes, cf. `_sweep`) purge en plus TOUTES les
    autres entrées et retire du dict celles dont la deque retombe à vide —
    trouvé en revue finale SP-26 (I4) : sous une vraie rotation de jeton
    OIDC, la clé d'appelant (l'en-tête Authorization brut) change à chaque
    refresh, quelques minutes ; purger seulement la deque de la clé
    courante ne suffit pas, une clé qui n'est plus jamais réutilisée après
    rotation ne serait plus jamais purgée du tout et resterait dans `_hits`
    pour toujours. Limite documentée qui reste, elle, réelle : ce compteur
    est par-process, sans partage entre répliques (pas de --workers
    aujourd'hui côté uvicorn, cf. C2/vague 0) — un déploiement
    multi-instance ne voit qu'une fraction du trafic par instance."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._calls_since_sweep = 0

    def _purge(self, bucket: deque[float], now: float) -> None:
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()

    def _sweep(self, now: float) -> None:
        stale_keys = []
        for bucket_key, bucket in self._hits.items():
            self._purge(bucket, now)
            if not bucket:
                stale_keys.append(bucket_key)
        for bucket_key in stale_keys:
            del self._hits[bucket_key]

    def allow(self, key: str, group: str) -> bool:
        budget = _BUDGETS[group]
        now = time.monotonic()
        bucket_key = (key, group)
        bucket = self._hits[bucket_key]
        self._purge(bucket, now)
        if len(bucket) >= budget:
            allowed = False
        else:
            bucket.append(now)
            allowed = True
        # bucket_key n'est jamais candidat au balayage ci-dessous : soit
        # `allowed` est False et bucket contient encore >= budget entrées
        # (jamais vide), soit `allowed` est True et `now` vient d'y être
        # ajouté (jamais vide non plus) — sûr d'appeler _sweep() après coup
        # sans risquer de supprimer l'entrée qu'on vient de peupler.
        self._calls_since_sweep += 1
        if self._calls_since_sweep >= _SWEEP_INTERVAL:
            self._sweep(now)
            self._calls_since_sweep = 0
        return allowed
