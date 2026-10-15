# SPDX-License-Identifier: Apache-2.0
"""Rate limiting en mémoire process, par (clé d'appelant, groupe de route)
— design SP-26 §3.4. Clé d'appelant = l'en-tête Authorization brut, pas un
user_id résolu : ce middleware tourne AVANT l'injection de dépendances
FastAPI (donc avant get_current_user), et /mcp est un mount ASGI brut sans
dépendances du tout — décoder/vérifier le JWT ici dupliquerait toute la
logique de app.auth.dependency pour un usage qui n'a besoin que d'une clé
stable, pas d'une identité vérifiée. Limite assumée : ne tient pas
multi-process (pas de --workers aujourd'hui côté uvicorn, cf. C2/vague 0)."""

import hashlib
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque

from sqlalchemy import Engine, create_engine, text

logger = logging.getLogger(__name__)

_SQL_RE = re.compile(r"^/v1/analytics/sql$")
# REV-336 : /aggregate, /profile et /export (agrégat) lancent du DuckDB (coût réel) — groupe dédié,
# budget plus large que "sql" car un tableau de bord émet un aggregate par widget.
_ANALYTICS_RE = re.compile(r"^/v1/collections/[^/]+/(aggregate|profile|export)$")
_LLM_RE = re.compile(r"^/mcp$|^/v1/copilot/turn$")
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
_HARVEST_RE = re.compile(r"^/v1/harvest/")
# GAP-58 (SP-45) : POST /collections/empty exécute un vrai CREATE TABLE
# PostGIS (DDL), accessible à tout utilisateur muni du privilège
# data.manage (pas seulement Administrateur) — aucun groupe existant ne le
# couvrait avant ce correctif.
_COLLECTIONS_EMPTY_RE = re.compile(r"^/v1/collections/empty$")
# GAP-61.b (SP-45) : les 2 routes de lecture ArcGIS live-query, seules
# authentiquement échappées au rate limiter (analyse-gaps.md affirmait 4,
# corrigé — 2 des 4 étaient déjà couvertes par _EXPORT_PATH_RE/"jobs").
# Peu importe la méthode HTTP (contrairement à _HARVEST_RE) : les deux
# déclenchent un appel sortant vers un service ArcGIS tiers, y compris la
# lecture GET .../items.
_ARCGIS_LIVE_QUERY_RE = re.compile(r"^/v1/datasets/[^/]+/arcgis/(items|aggregate)$")
# GAP-24, SP-53 : la seule route sans Depends(get_current_user) de tout le
# dépôt — un secret bearer par pipeline la protège à la place, mais elle
# doit aussi être son propre groupe de rate limiting (un appelant externe,
# CI ou capteur, peut avoir un profil d'appel différent des groupes
# existants).
_WEBHOOK_TRIGGER_RE = re.compile(r"^/v1/pipelines/[^/]+/trigger$")
# REV-275 (e) : GET /v1/share-links/{token} — route PUBLIQUE dont le jeton est
# dans le chemin ; clé IP seule (cf. caller_key), sinon varier le jeton
# contournerait le budget (même raisonnement que webhook-trigger, j06b-011).
_SHARE_LINK_RE = re.compile(r"^/v1/share-links/[^/]+$")
# REV-102 : GET /v1/geocode déclenche un appel sortant vers la Géoplateforme
# (BAN, 50 req/s/IP côté amont) — budget propre, le shell n'appelle qu'à la
# soumission du formulaire, jamais à la frappe.
_GEOCODE_RE = re.compile(r"^/v1/geocode(/batch|/reverse)?$")

# Budgets par groupe de coût réel (requêtes / 60s). Réutilise _EXPORT_PATH_RE
# de app.main pour le groupe "jobs" plutôt que de le redéfinir ici.
_BUDGETS = {
    "sql": 10,
    "analytics": 120,
    # Un tour de copilote coûte >= 4 requêtes (le tour + initialize/initialized/
    # list_tools en loopback /mcp, même clé Authorization) : 20 plafonnait à 5
    # tours/min puis 429 -> 502 (vu par l'e2e-oidc, 28 tours). 120 = ~30 tours/min.
    "llm": 120,
    "jobs": 15,
    "harvest": 10,
    "collections_empty": 5,
    "webhook-trigger": 30,
    "share-link": 60,
    "geocode": 60,
    # ARC-34 : compté par appel amont Valhalla (REST, MCP, ops de pipeline), pas par route ;
    # route_group ne le renvoie jamais, seul app.routing.client le consomme.
    "routing": 100,
}
_WINDOW_SECONDS = 60.0


def caller_key(
    auth_header: str | None,
    client_host: str | None,
    group: str | None = None,
    path: str | None = None,
) -> str:
    """Clé d'appelant pour le compteur glissant : l'en-tête Authorization
    brut s'il existe (comportement inchangé pour tout appelant authentifié),
    sinon l'IP réelle du visiteur (nécessite ProxyHeadersMiddleware côté
    app.main, cf. commentaire dédié) — jamais la chaîne vide partagée par
    tous les anonymes (GAP-61.a). Exception (j06b-011) : la route webhook-trigger
    est indexée sur IP + chemin (donc pipeline), jamais sur le jeton présenté —
    sinon varier le jeton à chaque essai contourne le budget (brute-force) ;
    idem pour share-link, indexée sur la seule IP."""
    if group == "webhook-trigger":
        return f"trigger:{client_host or 'unknown'}:{path}"
    if group == "share-link":
        return f"share:{client_host or 'unknown'}"
    if auth_header:
        return auth_header
    return f"anon:{client_host or 'unknown'}"


def route_group(
    path: str,
    method: str,
    export_path_re: re.Pattern[str],
    has_share_token: bool = False,
) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _ANALYTICS_RE.match(path):
        return "analytics"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if method == "POST" and _COLLECTIONS_EMPTY_RE.match(path):
        return "collections_empty"
    if _ARCGIS_LIVE_QUERY_RE.match(path):
        return "harvest"
    if _HARVEST_RE.match(path) and method != "GET":
        return "harvest"
    if _WEBHOOK_TRIGGER_RE.match(path) and method == "POST":
        return "webhook-trigger"
    if _SHARE_LINK_RE.match(path) and method == "GET":
        return "share-link"
    if _GEOCODE_RE.match(path):
        return "geocode"
    # REV-299 (c) : le jeton invité X-Share-Link-Token est aussi présenté en
    # en-tête sur les routes d'items/configs — même budget par IP que la route publique.
    # Les GET (tuiles MVT, items, configs, GeoJSON d'un embed) en sont exclus : une
    # carte en charge en émet des dizaines par vue et un 429 trouerait l'embed.
    if has_share_token and method != "GET":
        return "share-link"
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
        # REV-299 (b) : seuil share-link réglable (défaut 60/min).
        self._budgets = {
            **_BUDGETS,
            "share-link": int(os.environ.get("CORE_RATELIMIT_SHARE_LINK_PER_MIN") or 60),
        }
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
        budget = self._budgets[group]
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


# Disjoncteur : après un échec Postgres, on reste en repli local ce nombre de secondes plutôt
# que de payer le timeout à chaque requête.
_BREAKER_SECONDS = 5.0
_UPSERT = text(
    "INSERT INTO rate_limit_counters (key_hash, grp, window_start, hits) "
    "VALUES (:k, :g, :w, 1) "
    "ON CONFLICT (key_hash, grp, window_start) DO UPDATE "
    "SET hits = rate_limit_counters.hits + 1 RETURNING hits"
)


class PgRateLimiter(RateLimiter):
    """Limiteur partagé entre réplicas `core` (ARC-32) : compteur à fenêtre fixe de 60 s en
    UPSERT Postgres, un aller-retour par requête limitée. La clé (en-tête Authorization brut)
    n'est jamais stockée, seulement son SHA-256. Base lente ou injoignable : timeout court puis
    repli sur le compteur mémoire du process (budget par réplica, comportement ADR 0019) avec
    disjoncteur — la limitation ne doit jamais rendre l'API indisponible.
    ponytail: fenêtre fixe (jusqu'à 2x le budget à cheval sur deux fenêtres), fenêtre glissante
    pondérée si le besoin est mesuré."""

    def __init__(self, engine: Engine, *, timeout_ms: int = 250) -> None:
        super().__init__()
        self._engine = engine
        self._timeout_ms = timeout_ms
        self._open_until = 0.0
        self._calls_since_purge = 0
        # Le repli mémoire est appelé depuis le threadpool (run_in_threadpool) : RateLimiter n'est
        # pas thread-safe (_sweep itère _hits).
        self._local_lock = threading.Lock()

    @property
    def degraded(self) -> bool:
        return time.monotonic() < self._open_until

    def _allow_pg(self, key: str, group: str, budget: int) -> bool:
        window = int(time.time() // _WINDOW_SECONDS)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self._engine.begin() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {int(self._timeout_ms)}"))
            hits = conn.execute(_UPSERT, {"k": key_hash, "g": group, "w": window}).scalar_one()
            self._calls_since_purge += 1
            if self._calls_since_purge >= 500:
                self._calls_since_purge = 0
                conn.execute(
                    text("DELETE FROM rate_limit_counters WHERE window_start < :w"),
                    {"w": window - 1},
                )
        return bool(hits <= budget)

    def allow(self, key: str, group: str) -> bool:
        if not self.degraded:
            try:
                return self._allow_pg(key, group, self._budgets[group])
            except Exception:
                logger.warning("ratelimit: Postgres indisponible, repli local", exc_info=True)
                self._open_until = time.monotonic() + _BREAKER_SECONDS
        with self._local_lock:
            return super().allow(key, group)


def make_rate_limiter(database_url: str) -> RateLimiter:
    """CORE_RATELIMIT_BACKEND=postgres : budget partagé entre réplicas (ARC-32), sur un
    moteur dédié au pool minuscule (jamais en concurrence avec le pool des requêtes)."""
    if os.environ.get("CORE_RATELIMIT_BACKEND", "memory") == "postgres" and database_url.startswith(
        "postgresql"
    ):
        engine = create_engine(
            database_url,
            pool_size=2,
            max_overflow=2,
            pool_timeout=0.25,
            pool_pre_ping=True,
            # PgBouncer en mode transaction : pas de requêtes préparées côté serveur (psycopg 3
            # en pose une dès la 5e exécution) — vu au rejeu HA, repli mémoire silencieux sinon.
            connect_args={"prepare_threshold": None},
        )
        return PgRateLimiter(engine)
    return RateLimiter()
