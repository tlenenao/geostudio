# REV-102/GAP-08 — Géocodage BAN : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-08/REV-102 (chantier 4.13) : un contrôle de
recherche d'adresse (fournisseur BAN, `api-adresse.data.gouv.fr`), monté
dans l'éditeur de carte et dans le widget carte runtime de l'App Builder,
qui recentre/zoome la carte sur le résultat choisi — via une route proxy
du cœur gardée par une garde d'egress SSRF dédiée, jamais un appel direct
navigateur→BAN.

**Architecture:** Nouveau module `core/app/geocoding/` (contrat
`GeocodingProvider` enfichable, patron `LLMProvider`/`EmbeddingProvider` —
`provider.py` + `egress.py` + `routes.py`), une route inconditionnelle
`GET /v1/geocoding/search`, un groupe de rate-limit dédié ; côté shell,
deux nouveaux fichiers (`addressSearch.ts` logique pure +
`AddressSearchControl.tsx` composant) montés depuis `MapView.tsx` derrière
une nouvelle prop `addressSearch?: boolean`, elle-même passée par
`MapEditorPage.tsx` et `mapWidget.tsx` — même doctrine que la prop
`interactiveTools` déjà en place pour la barre mesure/croquis (SP-27).
Aucun changement à `ItemClient`/`MapConfig`/`AppConfig` : le fetch passe
en direct par `getCoreUrl`/`getAuthToken`, comme les pièces jointes de
popup et l'authentification tuiles 3D dans ce même fichier.

**Tech Stack:** Python/FastAPI + `httpx` (cœur, `httpx.Client` synchrone
gardé — déjà une dépendance, utilisé par `app.harvest.egress`/
`app.copilot.egress`) + pytest ; TypeScript/React + Vitest + Playwright
(shell). **Aucune nouvelle dépendance** des deux côtés.

**Document source :**
`docs/superpowers/specs/2026-09-07-rev102-geocodage-ban-design.md` (§1
cœur, §2 shell, §3 hors-scope, §Critères de sortie, §Hors périmètre).

## Global Constraints

- **Aucune capacité `CORE_..._ENABLED`** : la route est montée
  inconditionnellement (spec §Décision de scope, point 4).
- **Aucune méthode `ItemClient` nouvelle** : le contrôle carte fait son
  propre `fetch` via `getCoreUrl`/`getAuthToken`, jamais
  `useItemClient()` (spec §2.1/§3, patron déjà établi dans
  `MapView.tsx` pour les pièces jointes de popup).
- **Aucun champ `MapConfig`/`AppConfig` nouveau** : `addressSearch` est
  une prop de rendu passée par l'appelant, jamais persistée (même
  patron que `interactiveTools`).
- **TDD / filet-avant-code** systématique, un test qui échoue avant
  chaque implémentation.
- **Tout filet de test ajouté doit être vérifié par falsification**
  (piège CLAUDE.md n°10) : chaque tâche a une étape dédiée.
- Commits **conventional**, français (`feat(core): ...`, `test(core):
  ...`, `feat(shell): ...`).
- **Suite complète rejouée avant de clore chaque tâche cœur** :
  `cd core && uv run pytest` (ou ciblé sur le fichier de la tâche pendant
  l'itération, complet avant le commit de clôture de tâche) ; côté shell,
  `cd shell && npm run test` (Tâches 7-10), `npm run e2e -- <spec>` ciblé
  puis complet à la Tâche 11.
- **Régénérer la spec OpenAPI + types TS** (piège CLAUDE.md n°1) — Tâche
  6, seule tâche qui change la forme de l'API :
  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
  Diff **non vide** attendu à la Tâche 6 (une route + un schéma de
  réponse nouveaux) ; **vide** attendu si relancé par erreur aux Tâches
  1-5 ou 7-11 (aucune ne touche une route/un schéma).
- **`CORE_AUTH_MODE=mock` + `Authorization: Bearer mock:<sub>`** est le
  patron d'authentification de test déjà utilisé par
  `core/tests/test_copilot_routes.py` — le réutiliser tel quel plutôt que
  d'inventer un autre mécanisme (pas besoin du montage MCP-loopback
  complet de ce fichier, cette route n'a aucune dépendance MCP).
- **Écart volontaire vis-à-vis des 4 gardes d'egress existantes**
  (`app.harvest`/`app.pipelines`/`app.alerts`/`app.copilot`) : celles-ci
  autorisent tout hôte externe par défaut (allowlist vide = ouvert) ; la
  garde de ce plan retombe sur une allowlist par défaut **non vide**
  (`{"api-adresse.data.gouv.fr"}`) quand `CORE_GEOCODING_EGRESS_ALLOWLIST`
  n'est pas réglée (spec §1.2). Ne pas « corriger » cet écart par
  cohérence avec les autres gardes — c'est la décision, testée
  explicitement à la Tâche 1.
- **Piège CLAUDE.md n°4 (revue de branche)** : à la clôture, vérifier
  que `MapMeasureSketchToolbar` (mesure/croquis, SP-27) continue de se
  monter et de fonctionner sur les deux sites (`MapEditorPage.tsx`,
  `mapWidget.tsx`) après l'ajout de la prop `addressSearch` — pas
  seulement le nouveau contrôle testé isolément.

---

## Task 1 : `app.geocoding.egress` (garde SSRF, allowlist par défaut restrictive)

**Files:**
- Create: `core/app/geocoding/__init__.py` (vide)
- Create: `core/app/geocoding/egress.py`
- Test: `core/tests/test_geocoding_egress.py`

**Interfaces:**
- Produces: `assert_egress_allowed(url: str) -> None` (lève
  `EgressBlockedError`), `build_guarded_client(timeout: float = 10.0) ->
  httpx.Client`, `class EgressBlockedError(Exception)`.

- [ ] **Step 1 : écrire les tests (avant le code)**

Créer `core/tests/test_geocoding_egress.py`, patron
`core/tests/test_copilot_egress.py` (mêmes 7 cas d'IP internes + hôte non
HTTP + résolution DNS interne), **plus** les 2 cas propres à l'écart
assumé de ce module (allowlist par défaut non vide) :

```python
# SPDX-License-Identifier: Apache-2.0
import socket

import pytest

from app.geocoding.egress import EgressBlockedError, assert_egress_allowed


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
        "http://[fc00::1]/x",
        "http://0.0.0.0/x",
    ],
)
def test_assert_blocks_internal_ip_literals_without_dns(url):
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_allows_ban_host_by_default(monkeypatch):
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    assert_egress_allowed("https://api-adresse.data.gouv.fr/search/")


def test_assert_blocks_arbitrary_external_host_by_default(monkeypatch):
    # Écart assumé (spec §1.2) vis-à-vis des 4 gardes sœurs : ici
    # l'allowlist par défaut n'est PAS vide, donc un hôte externe
    # arbitraire non listé reste bloqué même sans réglage opérateur —
    # contrairement à app.harvest.egress/app.copilot.egress où l'absence
    # de réglage ouvre tout hôte externe.
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_respects_explicit_allowlist_override(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "mirror.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    assert_egress_allowed("https://mirror.example.com/search/")
    # Le réglage explicite REMPLACE le défaut : le miroir doit être
    # ajouté par l'opérateur, l'hôte BAN public n'est plus implicitement
    # permis dès qu'une allowlist explicite existe.
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://api-adresse.data.gouv.fr/search/")
```

```bash
cd core && uv run pytest tests/test_geocoding_egress.py -v
# attendu : ÉCHEC (ModuleNotFoundError: app.geocoding.egress)
```

- [ ] **Step 2 : implémenter**

`core/app/geocoding/__init__.py` : fichier vide.

`core/app/geocoding/egress.py` (copie de
`core/app/harvest/egress.py`, sans le plafond de taille de réponse —
justifié spec §1.2 —, allowlist par défaut non vide) :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF dédiée à `app.geocoding` (REV-102/GAP-08). Même
code que les 4 gardes sœurs (app.harvest/app.pipelines/app.alerts/
app.copilot.egress) pour la résolution DNS et le blocage des plages
réseau internes, mais **écart assumé** sur le comportement par défaut :
les 4 gardes sœurs autorisent tout hôte externe quand leur allowlist
n'est pas réglée (l'hôte cible y est fourni par un utilisateur ou un
opérateur). Ici l'hôte cible est fixé par le code
(BanGeocodingProvider.api_url) et ne varie que si un opérateur redéfinit
explicitement CORE_GEOCODING_BAN_URL — un réglage de déploiement, pas une
entrée utilisateur. Reproduire « vide = tout autoriser » ouvrirait donc
un SSRF total sur une route qui n'a jamais besoin de parler à autre
chose que la BAN. CORE_GEOCODING_EGRESS_ALLOWLIST retombe donc sur
{"api-adresse.data.gouv.fr"} quand elle n'est pas réglée — fail-closed
par défaut, à l'inverse des 4 gardes sœurs. Conséquence : un opérateur
qui redéfinit CORE_GEOCODING_BAN_URL vers un miroir auto-hébergé DOIT
aussi ajouter cet hôte à CORE_GEOCODING_EGRESS_ALLOWLIST, sinon la garde
bloque toute requête (échec explicite en 502, jamais un SSRF
silencieusement permis).

Pas de plafond de taille de réponse (contrairement à app.harvest.egress) :
la réponse BAN est bornée par construction (limit <= 20 côté route,
BAN refuse limit > 50), quelques kilooctets au pire — même choix
d'absence de plafond que app.copilot.egress/app.alerts.egress.

Résiduel documenté (identique aux 4 gardes sœurs) : TOCTOU DNS-rebinding
— la garde valide l'IP résolue avant la requête, httpx re-résout au
connect."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_GEOCODING_EGRESS_ALLOWLIST"
_DEFAULT_ALLOWLIST = frozenset({"api-adresse.data.gouv.fr"})


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    hosts = {h.strip() for h in raw.split(",") if h.strip()}
    return hosts if hosts else set(_DEFAULT_ALLOWLIST)


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_egress_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise EgressBlockedError(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise EgressBlockedError(f"hôte d'egress absent dans l'URL : {url!r}")

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise EgressBlockedError(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")

    allowlist = _allowlist()
    if host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        return self._inner.handle_request(request)


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(transport=_GuardedTransport(httpx.HTTPTransport()), timeout=timeout)
```

Note d'implémentation : `if host not in allowlist` (pas `if allowlist and
host not in allowlist` comme les 4 gardes sœurs) — puisque `_allowlist()`
ne renvoie **jamais** un ensemble vide ici (repli sur
`_DEFAULT_ALLOWLIST`), la condition `allowlist and` serait toujours vraie
et donc un bruit mort ; l'omettre rend le changement de comportement
visible à la lecture plutôt que caché dans une condition copiée-collée.

```bash
cd core && uv run pytest tests/test_geocoding_egress.py -v
# attendu : PASS (7 cas génériques + 3 cas spécifiques à ce module)
```

- [ ] **Step 3 : falsifier le filet d'allowlist par défaut restrictive**

Remplacer temporairement `return hosts if hosts else set(_DEFAULT_ALLOWLIST)`
par `return hosts` (reproduisant le comportement des 4 gardes sœurs) et
confirmer que `test_assert_blocks_arbitrary_external_host_by_default`
échoue (l'hôte arbitraire redevient autorisé). Remettre le code correct,
confirmer que la suite repasse au vert.

- [ ] **Step 4 : commit**

```bash
git add core/app/geocoding/__init__.py core/app/geocoding/egress.py \
  core/tests/test_geocoding_egress.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute la garde d'egress SSRF dédiée au géocodage

Ferme un volet de GAP-08/REV-102 (chantier 4.13) : 5e garde d'egress
du dépôt, même code que les 4 sœurs (harvest/pipelines/alerts/
copilot) mais allowlist par défaut restreinte à
api-adresse.data.gouv.fr (écart assumé, cf. docstring) — l'hôte cible
est fixé par le code, pas fourni par un utilisateur/opérateur comme
pour les 4 autres gardes.
EOF
)"
```

---

## Task 2 : `app.geocoding.provider` (contrat enfichable + fournisseur BAN)

**Files:**
- Create: `core/app/geocoding/provider.py`
- Test: `core/tests/test_geocoding_provider.py`

**Interfaces:**
- Consumes: `core.app.geocoding.egress.build_guarded_client` (Task 1).
- Produces: `GeocodeResult` (dataclass : `label: str, lon: float, lat:
  float, score: float, type: str, city: str | None = None, postcode: str
  | None = None`), `class GeocodingProvider(Protocol): def search(self,
  query: str, limit: int) -> list[GeocodeResult]: ...`,
  `class BanGeocodingProvider`, `get_geocoding_provider() ->
  GeocodingProvider`.

- [ ] **Step 1 : écrire les tests (avant le code)**

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.geocoding.provider import (
    BanGeocodingProvider,
    GeocodeResult,
    get_geocoding_provider,
)

# Payload réel observé (curl, 2026-09-07) pour
# ?q=12+rue+de+la+republique+Tulle&limit=1 — tronqué aux champs consommés.
_BAN_PAYLOAD = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [5.482758, 45.298546]},
            "properties": {
                "label": "12 Rue de la République 38210 Tullins",
                "score": 0.7638590615835777,
                "type": "housenumber",
                "city": "Tullins",
                "postcode": "38210",
            },
        }
    ],
    "query": "12 rue de la republique Tulle",
}


def test_ban_provider_parses_real_response_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "12 rue de la republique Tulle"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json=_BAN_PAYLOAD)

    provider = BanGeocodingProvider(
        api_url="https://api-adresse.data.gouv.fr/search/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    results = provider.search("12 rue de la republique Tulle", 1)
    assert results == [
        GeocodeResult(
            label="12 Rue de la République 38210 Tullins",
            lon=5.482758,
            lat=45.298546,
            score=0.7638590615835777,
            type="housenumber",
            city="Tullins",
            postcode="38210",
        )
    ]


def test_ban_provider_returns_empty_list_on_no_match():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [], "query": "x"})

    provider = BanGeocodingProvider(
        api_url="https://api-adresse.data.gouv.fr/search/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.search("zzzzzznonexistent", 5) == []


def test_ban_provider_raises_on_upstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 400, "message": "Failed parsing query"})

    provider = BanGeocodingProvider(
        api_url="https://api-adresse.data.gouv.fr/search/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        provider.search("", 5)


def test_ban_provider_defaults_missing_optional_fields():
    # properties.city/postcode absents sur un résultat "municipality" que
    # BAN peut renvoyer sans ces deux champs pour certaines communes —
    # ne doit jamais lever de KeyError.
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1.764073, 45.267177]},
                "properties": {"label": "Tulle", "score": 0.94, "type": "municipality"},
            }
        ],
        "query": "Tulle",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = BanGeocodingProvider(
        api_url="https://api-adresse.data.gouv.fr/search/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    [result] = provider.search("Tulle", 1)
    assert result.city is None
    assert result.postcode is None


def test_get_geocoding_provider_defaults_to_ban(monkeypatch):
    monkeypatch.delenv("CORE_GEOCODING_PROVIDER", raising=False)
    provider = get_geocoding_provider()
    assert isinstance(provider, BanGeocodingProvider)


def test_get_geocoding_provider_accepts_explicit_ban(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_PROVIDER", "ban")
    assert isinstance(get_geocoding_provider(), BanGeocodingProvider)


def test_get_geocoding_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_PROVIDER", "google")
    with pytest.raises(ValueError, match="CORE_GEOCODING_PROVIDER"):
        get_geocoding_provider()


def test_get_geocoding_provider_reads_custom_ban_url(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_BAN_URL", "https://mirror.example.com/search/")
    provider = get_geocoding_provider()
    assert isinstance(provider, BanGeocodingProvider)
    assert provider._api_url == "https://mirror.example.com/search/"
```

```bash
cd core && uv run pytest tests/test_geocoding_provider.py -v
# attendu : ÉCHEC (ModuleNotFoundError: app.geocoding.provider)
```

- [ ] **Step 2 : implémenter**

```python
# SPDX-License-Identifier: Apache-2.0
"""Fournisseur de géocodage enfichable (REV-102/GAP-08), même convention
que app.search.providers.EmbeddingProvider (SP-7) et
app.copilot.llm_provider.LLMProvider (SP-20) : un Protocol, une
implémentation réseau, un réglage par variable d'environnement.

Synchrone par contrat (contrairement à LLMProvider.chat, async) : un
aller-retour HTTP unique et rapide, exécuté par une route FastAPI `def`
(pas `async def`) dans le threadpool de FastAPI — même choix que
app.harvest.live_query.fetch_query et les routes GET
/datasets/{id}/arcgis/items."""

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.geocoding.egress import build_guarded_client

_DEFAULT_BAN_URL = "https://api-adresse.data.gouv.fr/search/"


@dataclass(frozen=True)
class GeocodeResult:
    label: str
    lon: float
    lat: float
    score: float
    type: str
    city: str | None = None
    postcode: str | None = None


class GeocodingProvider(Protocol):
    def search(self, query: str, limit: int) -> list[GeocodeResult]: ...


class BanGeocodingProvider:
    def __init__(self, *, api_url: str, http_client: httpx.Client | None = None):
        self._api_url = api_url
        # Client injectable (même couture que OpenAICompatibleLLMProvider) :
        # sinon un client éphémère par appel, gardé (build_guarded_client)
        # quand aucun n'est fourni.
        self._client = http_client

    def search(self, query: str, limit: int) -> list[GeocodeResult]:
        params = {"q": query, "limit": str(limit)}
        if self._client is not None:
            response = self._client.get(self._api_url, params=params)
        else:
            with build_guarded_client() as client:
                response = client.get(self._api_url, params=params)
        response.raise_for_status()
        data = response.json()
        return [
            GeocodeResult(
                label=f["properties"]["label"],
                lon=f["geometry"]["coordinates"][0],
                lat=f["geometry"]["coordinates"][1],
                score=f["properties"].get("score", 0.0),
                type=f["properties"].get("type", "unknown"),
                city=f["properties"].get("city"),
                postcode=f["properties"].get("postcode"),
            )
            for f in data.get("features", [])
        ]


def get_geocoding_provider() -> GeocodingProvider:
    kind = os.environ.get("CORE_GEOCODING_PROVIDER")
    if kind is None or kind == "ban":
        api_url = os.environ.get("CORE_GEOCODING_BAN_URL", _DEFAULT_BAN_URL)
        return BanGeocodingProvider(api_url=api_url)
    raise ValueError(f"unknown CORE_GEOCODING_PROVIDER: {kind}")
```

```bash
cd core && uv run pytest tests/test_geocoding_provider.py -v
# attendu : PASS
```

- [ ] **Step 3 : falsifier le filet de champs optionnels manquants**

Retirer temporairement les `.get("city")`/`.get("postcode")` au profit de
`["city"]`/`["postcode"]`, confirmer que
`test_ban_provider_defaults_missing_optional_fields` échoue avec un
`KeyError`, remettre le code correct.

- [ ] **Step 4 : commit**

```bash
git add core/app/geocoding/provider.py core/tests/test_geocoding_provider.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le fournisseur de géocodage enfichable (BAN)

Ferme un volet de GAP-08/REV-102 : contrat GeocodingProvider (patron
LLMProvider/EmbeddingProvider), implémentation BanGeocodingProvider
contre l'API réelle api-adresse.data.gouv.fr (forme de réponse
vérifiée par curl avant d'écrire ce plan), get_geocoding_provider()
lisant CORE_GEOCODING_PROVIDER (défaut/valeur "ban" uniquement
aujourd'hui).
EOF
)"
```

---

## Task 3 : `app.geocoding.routes` (`GET /geocoding/search`) + montage + contrat de couches

**Files:**
- Create: `core/app/geocoding/routes.py`
- Modify: `core/app/main.py` (import + `v1_router.include_router`)
- Modify: `core/pyproject.toml` (`[[tool.importlinter.contracts]]
  layers`)
- Test: `core/tests/test_geocoding_routes.py`

**Interfaces:**
- Consumes: `app.geocoding.provider.get_geocoding_provider`,
  `app.geocoding.egress.EgressBlockedError` (Tasks 1-2),
  `app.auth.dependency.get_current_user`, `app.users.models.User`.
- Produces: `router: APIRouter` monté par `app.main.create_app()`.

- [ ] **Step 1 : écrire les tests (avant le code)**

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import GeocodeResult
from app.main import create_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app)
    test_client.headers["Authorization"] = "Bearer mock:alice"
    return test_client


class _FakeProvider:
    def __init__(self, results=None, raise_exc=None):
        self._results = results or []
        self._raise_exc = raise_exc

    def search(self, query, limit):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._results


def test_search_requires_authentication():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    anon_client = TestClient(app)
    res = anon_client.get("/v1/geocoding/search?q=Tulle")
    assert res.status_code == 401


def test_search_returns_normalized_results(client, monkeypatch):
    import app.geocoding.routes as routes_module

    monkeypatch.setattr(
        routes_module,
        "get_geocoding_provider",
        lambda: _FakeProvider(
            results=[
                GeocodeResult(
                    label="12 Rue de la République 19000 Tulle",
                    lon=1.764073,
                    lat=45.267177,
                    score=0.9,
                    type="housenumber",
                    city="Tulle",
                    postcode="19000",
                )
            ]
        ),
    )
    res = client.get("/v1/geocoding/search?q=12+rue+de+la+republique+Tulle")
    assert res.status_code == 200
    body = res.json()
    assert body["results"] == [
        {
            "label": "12 Rue de la République 19000 Tulle",
            "lon": 1.764073,
            "lat": 45.267177,
            "score": 0.9,
            "type": "housenumber",
            "city": "Tulle",
            "postcode": "19000",
        }
    ]


def test_search_rejects_empty_query(client):
    res = client.get("/v1/geocoding/search?q=")
    assert res.status_code == 422


def test_search_rejects_missing_query(client):
    res = client.get("/v1/geocoding/search")
    assert res.status_code == 422


def test_search_rejects_limit_above_cap(client):
    res = client.get("/v1/geocoding/search?q=Tulle&limit=21")
    assert res.status_code == 422


def test_search_returns_502_on_egress_blocked(client, monkeypatch):
    import app.geocoding.routes as routes_module

    monkeypatch.setattr(
        routes_module,
        "get_geocoding_provider",
        lambda: _FakeProvider(raise_exc=EgressBlockedError("hôte hors allowlist")),
    )
    res = client.get("/v1/geocoding/search?q=Tulle")
    assert res.status_code == 502


def test_search_returns_502_on_upstream_http_error(client, monkeypatch):
    import app.geocoding.routes as routes_module

    monkeypatch.setattr(
        routes_module,
        "get_geocoding_provider",
        lambda: _FakeProvider(
            raise_exc=httpx.HTTPStatusError(
                "boom", request=httpx.Request("GET", "https://x"), response=httpx.Response(400)
            )
        ),
    )
    res = client.get("/v1/geocoding/search?q=Tulle")
    assert res.status_code == 502
```

```bash
cd core && uv run pytest tests/test_geocoding_routes.py -v
# attendu : ÉCHEC (ModuleNotFoundError: app.geocoding.routes ; la route
# /v1/geocoding/search n'existe pas encore, 404 partout)
```

- [ ] **Step 2 : implémenter `routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""GET /geocoding/search — REV-102/GAP-08. Route inconditionnelle
(aucune capacité CORE_..._ENABLED, spec §Décision de scope point 4) :
gratuite, sans clé, sans configuration requise. Aucune garde de
privilège au-delà de l'authentification, même niveau que GET
/harvest/layers (lecture pure, sans donnée sensible du tenant)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependency import get_current_user
from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import get_geocoding_provider
from app.users.models import User

router = APIRouter()

_MAX_LIMIT = 20
_MAX_QUERY_CHARS = 200


class GeocodeResultOut(BaseModel):
    label: str
    lon: float
    lat: float
    score: float
    type: str
    city: str | None = None
    postcode: str | None = None


class GeocodeSearchResponse(BaseModel):
    results: list[GeocodeResultOut]


@router.get("/geocoding/search")
def search_address(
    q: str = Query(..., min_length=1, max_length=_MAX_QUERY_CHARS),
    limit: int = Query(5, ge=1, le=_MAX_LIMIT),
    user: User = Depends(get_current_user),
) -> GeocodeSearchResponse:
    provider = get_geocoding_provider()
    try:
        results = provider.search(q, limit)
    except EgressBlockedError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"garde d'egress géocodage : cible bloquée ({exc})",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="service de géocodage indisponible"
        ) from exc
    return GeocodeSearchResponse(
        results=[
            GeocodeResultOut(
                label=r.label,
                lon=r.lon,
                lat=r.lat,
                score=r.score,
                type=r.type,
                city=r.city,
                postcode=r.postcode,
            )
            for r in results
        ]
    )
```

- [ ] **Step 3 : monter la route dans `core/app/main.py`**

Ajouter l'import à côté des autres routeurs de domaine (chercher la ligne
`from app.harvest import routes as harvest_routes` ou équivalent voisin) :

```python
from app.geocoding import routes as geocoding_routes
```

Ajouter, dans le bloc **inconditionnel** de `v1_router.include_router(...)`
(à côté de `harvest_routes.router`/`stac_routes.router`/`dcat_routes.router`
— **pas** dans le bloc `if is_..._enabled():` en bas de la fonction) :

```python
    v1_router.include_router(geocoding_routes.router)
```

- [ ] **Step 4 : ajouter `app.geocoding` au contrat de couches**

Dans `core/pyproject.toml`, `[[tool.importlinter.contracts]] layers`,
insérer `"app.geocoding",` juste après `"app.harvest",` et avant
`"app.pipelines",` :

```toml
    "app.harvest",
    "app.geocoding",
    "app.pipelines",
```

Aucune entrée `ignore_imports` nécessaire (le module n'importe que
`app.auth.dependency`/`app.users.models`, tous deux plus bas dans le
contrat).

```bash
cd core && uv run pytest tests/test_geocoding_routes.py -v
# attendu : PASS
cd core && uv run lint-imports
# attendu : PASS (aucune violation de couches)
```

- [ ] **Step 5 : falsifier le filet d'authentification requise**

Retirer temporairement `user: User = Depends(get_current_user)` de la
signature de `search_address` (et l'argument correspondant), confirmer
que `test_search_requires_authentication` échoue (la route répond 200 au
lieu de 401 à un appel anonyme), remettre le code correct.

- [ ] **Step 6 : suite complète + commit**

```bash
cd core && uv run pytest
```

```bash
git add core/app/geocoding/routes.py core/app/main.py core/pyproject.toml \
  core/tests/test_geocoding_routes.py
git commit -m "$(cat <<'EOF'
feat(core): monte GET /geocoding/search (REV-102/GAP-08)

Route inconditionnelle (aucune capacité CORE_..._ENABLED requise),
authentification seule comme GET /harvest/layers. app.geocoding
inséré dans le contrat de couches juste sous app.harvest, aucune
exemption nécessaire.
EOF
)"
```

---

## Task 4 : rate limiting (`app/ratelimit/limiter.py`)

**Files:**
- Modify: `core/app/ratelimit/limiter.py`
- Test: `core/tests/test_ratelimit.py`

**Interfaces:**
- Consumes: rien de nouveau (module autonome).
- Produces: `route_group("/v1/geocoding/search", "GET", ...) ==
  "geocoding"`.

- [ ] **Step 1 : écrire les tests (avant le code)**

Ajouter dans `core/tests/test_ratelimit.py`, à côté des tests
`test_route_group_covers_arcgis_live_query_regardless_of_method` :

```python
def test_route_group_covers_geocoding_search():
    assert route_group("/v1/geocoding/search", "GET", _EXPORT_PATH_RE) == "geocoding"


def test_route_group_ignores_unrelated_geocoding_paths():
    assert route_group("/v1/geocoding/other", "GET", _EXPORT_PATH_RE) is None
```

```bash
cd core && uv run pytest tests/test_ratelimit.py -k geocoding -v
# attendu : ÉCHEC (assert None == "geocoding")
```

- [ ] **Step 2 : implémenter**

Dans `core/app/ratelimit/limiter.py`, à côté de `_ARCGIS_LIVE_QUERY_RE` :

```python
# REV-102/GAP-08 : même classe de risque que les 2 routes ArcGIS
# live-query (GAP-61.b, SP-45) — un appel sortant tiers déclenché par un
# GET, potentiellement à chaque frappe si le contrôle carte ne débounce
# pas correctement côté client (précédent : LayerPicker.tsx, cf.
# commentaire _HARVEST_RE ci-dessus). Le contrôle debounce bien côté
# client (350 ms, 3 caractères minimum), mais un budget serveur reste la
# seule protection qui ne dépend pas du bon comportement du client.
_GEOCODING_RE = re.compile(r"^/v1/geocoding/search$")
```

Ajouter à `_BUDGETS` :

```python
_BUDGETS = {
    "sql": 10,
    "llm": 20,
    "jobs": 15,
    "harvest": 10,
    "collections_empty": 5,
    "webhook-trigger": 30,
    "geocoding": 20,
}
```

Ajouter dans `route_group`, avant le `return None` final :

```python
    if _GEOCODING_RE.match(path):
        return "geocoding"
```

```bash
cd core && uv run pytest tests/test_ratelimit.py -v
# attendu : PASS
```

- [ ] **Step 3 : falsifier le filet**

Retirer temporairement le bloc `if _GEOCODING_RE.match(path): return
"geocoding"`, confirmer que `test_route_group_covers_geocoding_search`
échoue, remettre.

- [ ] **Step 4 : commit**

```bash
git add core/app/ratelimit/limiter.py core/tests/test_ratelimit.py
git commit -m "$(cat <<'EOF'
feat(core): rattache GET /geocoding/search à son propre groupe de
rate-limit

Même classe de risque que les 2 routes ArcGIS live-query (GAP-61.b) :
un GET déclenchant un appel sortant tiers, potentiellement à chaque
frappe si le débounce client échoue.
EOF
)"
```

---

## Task 5 : variables d'environnement (`.env.example`, `docker-compose.yml`)

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `CORE_GEOCODING_PROVIDER`, `CORE_GEOCODING_BAN_URL`,
  `CORE_GEOCODING_EGRESS_ALLOWLIST` (déjà lues par le code des Tasks 2-3
  via `os.environ.get`/la constante `_ALLOWLIST_ENV`).
- Produces: rien de nouveau — cette tâche rend ces 3 variables
  atteignables (`test_every_core_env_var_is_wired_to_a_service`).

- [ ] **Step 1 : ajouter à `.env.example`**

À côté du bloc `# ─── Cœur : copilote IA embarqué (SP-20) ─────` :

```
# ─── Cœur : géocodage (REV-102/GAP-08) ─────────────────
# Vide (défaut) ou "ban" : seul fournisseur implémenté aujourd'hui, sans
# clé ni configuration (api-adresse.data.gouv.fr, service public gratuit).
CORE_GEOCODING_PROVIDER=

# Vide (défaut) : URL publique BAN en dur dans le code. À ne changer que
# pour un miroir auto-hébergé de la même API.
CORE_GEOCODING_BAN_URL=

# Allowlist d'hôtes de la garde d'egress SSRF dédiée au géocodage — liste
# séparée par des virgules. ATTENTION, sémantique DIFFÉRENTE de
# CORE_LLM_EGRESS_ALLOWLIST/CORE_HARVEST_EGRESS_ALLOWLIST ci-dessus : ici
# vide (défaut) = SEUL api-adresse.data.gouv.fr est autorisé (l'hôte
# cible n'est jamais fourni par un utilisateur, contrairement au
# moissonnage/aux webhooks/au LLM). Redéfinir CORE_GEOCODING_BAN_URL vers
# un miroir sans AUSSI ajouter son hôte ici bloque toute requête (échec
# explicite en 502).
CORE_GEOCODING_EGRESS_ALLOWLIST=
```

- [ ] **Step 2 : câbler sur le service `core` de `docker-compose.yml`**

À côté du bloc `CORE_LLM_PROVIDER: ${CORE_LLM_PROVIDER:-}` (service
`core` uniquement — pas `worker`, aucun job asynchrone n'est concerné) :

```yaml
      CORE_GEOCODING_PROVIDER: ${CORE_GEOCODING_PROVIDER:-}
      CORE_GEOCODING_BAN_URL: ${CORE_GEOCODING_BAN_URL:-}
      CORE_GEOCODING_EGRESS_ALLOWLIST: ${CORE_GEOCODING_EGRESS_ALLOWLIST:-}
```

- [ ] **Step 3 : vérifier `test_deployability.py`**

```bash
cd core && uv run pytest tests/test_deployability.py -k env_var -v
# attendu : PASS (les 3 variables sont maintenant lues par core/app/,
# câblées sur un service, et documentées dans .env.example)
```

- [ ] **Step 4 : falsifier le filet**

Retirer temporairement les 3 lignes ajoutées à `docker-compose.yml`
(garder `.env.example`), confirmer que
`test_every_core_env_var_is_wired_to_a_service` échoue en listant les 3
variables comme non câblées, remettre les 3 lignes.

- [ ] **Step 5 : commit**

```bash
git add .env.example docker-compose.yml
git commit -m "$(cat <<'EOF'
feat(core): câble les 3 variables d'environnement du géocodage

CORE_GEOCODING_PROVIDER/CORE_GEOCODING_BAN_URL/
CORE_GEOCODING_EGRESS_ALLOWLIST, toutes optionnelles (défauts
fonctionnels sans rien régler) — service core uniquement.
EOF
)"
```

---

## Task 6 : régénération OpenAPI + types TS

**Files:**
- Modify: `core/openapi.json` (généré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (généré)

**Interfaces:** aucune, tâche de régénération pure.

- [ ] **Step 1 : régénérer**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 2 : vérifier le diff**

```bash
git diff --stat -- core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : diff **non vide**, limité à l'ajout de la route
`/v1/geocoding/search` et des schémas `GeocodeResultOut`/
`GeocodeSearchResponse` (ou noms générés équivalents) — aucun schéma
existant ne doit changer de forme (spec §3, aucun champ `MapConfig`/
`AppConfig` touché).

- [ ] **Step 3 : commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
chore(core): régénère la spec OpenAPI + les types TS (géocodage)

GET /v1/geocoding/search, seule route/schéma nouveaux — aucun schéma
existant ne change de forme.
EOF
)"
```

---

## Task 7 : `shell/src/map/addressSearch.ts` (logique pure)

**Files:**
- Create: `shell/src/map/addressSearch.ts`
- Test: `shell/src/map/addressSearch.test.ts`

**Interfaces:**
- Produces: `type GeocodeResult = { label: string; lon: number; lat:
  number; score: number; type: string; city?: string; postcode?: string
  }`, `zoomForResultType(type: string): number`, `searchAddress(coreUrl:
  string, getAuthToken: (() => string | undefined) | undefined, query:
  string, limit?: number): Promise<GeocodeResult[]>`.

- [ ] **Step 1 : écrire les tests (avant le code)**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { searchAddress, zoomForResultType } from "./addressSearch";

describe("zoomForResultType", () => {
  it("zoome fort sur une adresse précise", () => {
    expect(zoomForResultType("housenumber")).toBe(17);
    expect(zoomForResultType("street")).toBe(17);
  });
  it("zoome moins sur un lieu-dit", () => {
    expect(zoomForResultType("locality")).toBe(14);
  });
  it("zoome encore moins sur une commune", () => {
    expect(zoomForResultType("municipality")).toBe(13);
  });
  it("retombe sur le zoom le plus prudent pour un type inconnu", () => {
    expect(zoomForResultType("something-new")).toBe(12);
  });
});

describe("searchAddress", () => {
  it("appelle /geocoding/search sur coreUrl, avec le jeton si fourni", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            label: "12 Rue de la République 19000 Tulle",
            lon: 1.764073,
            lat: 45.267177,
            score: 0.9,
            type: "housenumber",
            city: "Tulle",
            postcode: "19000",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const results = await searchAddress(
      "https://core.test/v1",
      () => "tok",
      "12 rue de la République, Tulle",
      5,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "https://core.test/v1/geocoding/search?q=12%20rue%20de%20la%20R%C3%A9publique%2C%20Tulle&limit=5",
      { headers: { Authorization: "Bearer tok" } },
    );
    expect(results).toEqual([
      {
        label: "12 Rue de la République 19000 Tulle",
        lon: 1.764073,
        lat: 45.267177,
        score: 0.9,
        type: "housenumber",
        city: "Tulle",
        postcode: "19000",
      },
    ]);
  });

  it("n'envoie aucun en-tête Authorization sans jeton", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [] }) });
    vi.stubGlobal("fetch", fetchMock);

    await searchAddress("https://core.test/v1", undefined, "Tulle");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://core.test/v1/geocoding/search?q=Tulle&limit=5",
      { headers: {} },
    );
  });

  it("lève une erreur explicite sur une réponse non OK", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 502 });
    vi.stubGlobal("fetch", fetchMock);

    await expect(searchAddress("https://core.test/v1", undefined, "Tulle")).rejects.toThrow(
      "Request failed: 502 geocoding/search",
    );
  });

  it("renvoie un tableau vide si `results` est absent de la réponse", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    expect(await searchAddress("https://core.test/v1", undefined, "Tulle")).toEqual([]);
  });
});
```

```bash
cd shell && npm run test -- addressSearch.test.ts
# attendu : ÉCHEC (module addressSearch.ts introuvable)
```

- [ ] **Step 2 : implémenter**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Logique pure du contrôle de recherche d'adresse (REV-102/GAP-08),
// séparée du composant React comme measureSketch.ts/
// MapMeasureSketchToolbar.tsx (SP-27) — testable sans DOM.

export type GeocodeResult = {
  label: string;
  lon: number;
  lat: number;
  score: number;
  type: string;
  city?: string;
  postcode?: string;
};

// Heuristique de zoom par type BAN (valeurs observées empiriquement :
// housenumber/street/locality/municipality). Un type non listé (futur
// fournisseur, ou valeur BAN non documentée) retombe sur le zoom le plus
// dézoomé, jamais une exception.
export function zoomForResultType(type: string): number {
  switch (type) {
    case "housenumber":
    case "street":
      return 17;
    case "locality":
      return 14;
    case "municipality":
      return 13;
    default:
      return 12;
  }
}

// `coreUrl` est attendu déjà versionné (".../v1"), comme le champ que
// `getCoreUrl()` renvoie côté MapView (cf. createBase() shell/src/api/base.ts).
export async function searchAddress(
  coreUrl: string,
  getAuthToken: (() => string | undefined) | undefined,
  query: string,
  limit = 5,
): Promise<GeocodeResult[]> {
  const token = getAuthToken?.();
  const url = `${coreUrl}/geocoding/search?q=${encodeURIComponent(query)}&limit=${limit}`;
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Request failed: ${res.status} geocoding/search`);
  const data = (await res.json()) as { results?: GeocodeResult[] };
  return data.results ?? [];
}
```

```bash
cd shell && npm run test -- addressSearch.test.ts
# attendu : PASS
```

- [ ] **Step 3 : falsifier le filet du zoom par défaut**

Remplacer temporairement `default: return 12;` par `default: return
zoomForResultType("municipality");` (ou toute valeur qui coïncide par
erreur avec un des cas déjà couverts), confirmer que le test « type
inconnu » échoue s'il ne coïncide pas — si le test passe malgré la
régression injectée, le test est trop faible, le corriger. Remettre le
code correct.

- [ ] **Step 4 : commit**

```bash
git add shell/src/map/addressSearch.ts shell/src/map/addressSearch.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute la logique pure de recherche d'adresse (BAN)

searchAddress()/zoomForResultType(), consommées par
AddressSearchControl (tâche suivante) — patron measureSketch.ts :
logique testable sans DOM, séparée du composant React.
EOF
)"
```

---

## Task 8 : `shell/src/map/AddressSearchControl.tsx` (composant) + i18n

**Files:**
- Create: `shell/src/map/AddressSearchControl.tsx`
- Test: `shell/src/map/AddressSearchControl.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `searchAddress`, `GeocodeResult` (Task 7).
- Produces: `AddressSearchControl({ getCoreUrl, getAuthToken, onSelect
  }: { getCoreUrl?: () => string; getAuthToken?: () => string |
  undefined; onSelect: (result: GeocodeResult) => void })`.

- [ ] **Step 1 : ajouter les clés i18n**

Dans `shell/src/i18n/catalog.fr.ts`, à côté des clés `mapMeasure.*` :

```typescript
  "addressSearch.placeholder": "Rechercher une adresse…",
  "addressSearch.noResults": "Aucune adresse trouvée.",
  "addressSearch.error": "La recherche d'adresse a échoué.",
  "addressSearch.resultsLabel": "Résultats de la recherche d'adresse",
```

- [ ] **Step 2 : écrire les tests (avant le code)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddressSearchControl } from "./AddressSearchControl";

describe("AddressSearchControl", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("ne déclenche aucune requête sous 3 caractères", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AddressSearchControl
        getCoreUrl={() => "https://core.test/v1"}
        getAuthToken={() => "tok"}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
      target: { value: "Tu" },
    });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("débounce 350 ms avant d'appeler searchAddress à partir de 3 caractères", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          { label: "Tulle", lon: 1.76, lat: 45.27, score: 0.9, type: "municipality" },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AddressSearchControl
        getCoreUrl={() => "https://core.test/v1"}
        getAuthToken={() => "tok"}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
      target: { value: "Tulle" },
    });
    await vi.advanceTimersByTimeAsync(340);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(20);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Tulle")).toBeInTheDocument();
  });

  it("appelle onSelect avec le résultat cliqué et vide la liste", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          { label: "Tulle", lon: 1.76, lat: 45.27, score: 0.9, type: "municipality" },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSelect = vi.fn();
    render(
      <AddressSearchControl
        getCoreUrl={() => "https://core.test/v1"}
        getAuthToken={() => "tok"}
        onSelect={onSelect}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
      target: { value: "Tulle" },
    });
    await vi.advanceTimersByTimeAsync(360);
    const result = await screen.findByText("Tulle");
    fireEvent.click(result);
    expect(onSelect).toHaveBeenCalledWith({
      label: "Tulle",
      lon: 1.76,
      lat: 45.27,
      score: 0.9,
      type: "municipality",
    });
    expect(screen.queryByText("Tulle")).not.toBeInTheDocument();
  });

  it("affiche un message d'erreur si la requête échoue", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));
    render(
      <AddressSearchControl
        getCoreUrl={() => "https://core.test/v1"}
        getAuthToken={() => "tok"}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
      target: { value: "Tulle" },
    });
    await vi.advanceTimersByTimeAsync(360);
    expect(await screen.findByText("La recherche d'adresse a échoué.")).toBeInTheDocument();
  });

  it("ne fait jamais de requête sans getCoreUrl (export statique)", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AddressSearchControl onSelect={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
      target: { value: "Tulle" },
    });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
```

```bash
cd shell && npm run test -- AddressSearchControl.test.tsx
# attendu : ÉCHEC (module AddressSearchControl.tsx introuvable)
```

- [ ] **Step 3 : implémenter**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { searchAddress, type GeocodeResult } from "./addressSearch";
import { t } from "../i18n";

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 3;

export function AddressSearchControl({
  getCoreUrl,
  getAuthToken,
  onSelect,
}: {
  getCoreUrl?: () => string;
  getAuthToken?: () => string | undefined;
  onSelect: (result: GeocodeResult) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function handleChange(value: string) {
    setQuery(value);
    setError(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (value.trim().length < MIN_QUERY_LENGTH || !getCoreUrl) {
      setResults([]);
      return;
    }
    timerRef.current = setTimeout(() => {
      searchAddress(getCoreUrl(), getAuthToken, value)
        .then(setResults)
        .catch(() => {
          setResults([]);
          setError(true);
        });
    }, DEBOUNCE_MS);
  }

  function handleSelect(result: GeocodeResult) {
    onSelect(result);
    setResults([]);
    setQuery(result.label);
  }

  return (
    <div className="absolute left-2 top-2 z-10 w-64">
      <input
        type="text"
        value={query}
        placeholder={t("addressSearch.placeholder")}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full rounded border border-line bg-surface px-2 py-1 text-sm"
        aria-label={t("addressSearch.placeholder")}
      />
      {error && <p className="mt-1 text-xs text-danger">{t("addressSearch.error")}</p>}
      {!error && results.length > 0 && (
        <ul
          aria-label={t("addressSearch.resultsLabel")}
          className="mt-1 max-h-64 overflow-y-auto rounded border border-line bg-surface text-sm shadow"
        >
          {results.map((r, i) => (
            <li key={`${r.label}-${i}`}>
              <button
                type="button"
                className="w-full px-2 py-1 text-left hover:bg-surface-2"
                onClick={() => handleSelect(r)}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

Note : classes utilitaires (`border-line`, `bg-surface`, `text-danger`,
`bg-surface-2`) à vérifier/ajuster contre les tokens réellement définis
dans `shell/src/styles/tokens.css` au moment de l'implémentation (SP-29a) —
ne jamais introduire de couleur Tailwind brute (`text-slate-400` etc.),
piège documenté par SP-57a.

```bash
cd shell && npm run test -- AddressSearchControl.test.tsx
# attendu : PASS
```

- [ ] **Step 4 : falsifier le filet de debounce**

Remplacer temporairement `DEBOUNCE_MS = 350` par `DEBOUNCE_MS = 0`,
confirmer que le test « ne déclenche aucune requête sous 3 caractères »
passe toujours (c'est le seuil de longueur qui protège, pas le debounce)
mais que le test « débounce 350 ms... » échoue (l'appel arrive avant
340 ms). Remettre `DEBOUNCE_MS = 350`.

- [ ] **Step 5 : vérifier la couverture i18n**

```bash
cd shell && node scripts/check-i18n-coverage.mjs
# attendu : aucune chaîne française codée en dur détectée dans
# AddressSearchControl.tsx (toutes via t())
```

- [ ] **Step 6 : commit**

```bash
git add shell/src/map/AddressSearchControl.tsx \
  shell/src/map/AddressSearchControl.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le composant de recherche d'adresse

AddressSearchControl : champ texte débounced (350 ms, 3 caractères
minimum), liste de résultats cliquables, dégrade silencieusement sans
getCoreUrl (export statique sans cœur). i18n complet (t()).
EOF
)"
```

---

## Task 9 : `shell/src/map/MapView.tsx` (prop `addressSearch`)

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `AddressSearchControl`, `zoomForResultType` (Tasks 7-8).
- Produces: nouvelle prop `addressSearch?: boolean` sur `MapView`.

- [ ] **Step 1 : écrire le test (avant le code)**

Ajouter dans `shell/src/map/MapView.test.tsx`, juste après les deux tests
existants `"la barre mesure/croquis est montée quand interactiveTools est
vrai"`/`"la barre mesure/croquis est absente par défaut"` (ligne ~2240) —
même patron exact : `mapInstances` (déjà importé en tête de fichier
depuis `../test/MockMaplibreMap`) expose `flyToArgs: unknown[]`
(alimenté par `MockMap.flyTo()`, déjà consommé par le test
`"exposes an imperative flyTo that drives the map"` ligne 441) et le
mock de `maplibre-gl` (ligne 17) fait que le handler `"load"` est appelé
**synchroniquement** à l'enregistrement (`MockMaplibreMap.ts:59`), donc
`readyMap` est déjà posé au premier rendu — pas besoin de `waitFor`/`act`
pour le montage initial, comme les deux tests voisins déjà cités :

```tsx
test("le contrôle de recherche d'adresse n'est pas monté sans la prop addressSearch", () => {
  render(<MapView config={config} />);
  expect(screen.queryByPlaceholderText("Rechercher une adresse…")).not.toBeInTheDocument();
});

test("le contrôle de recherche d'adresse est monté quand addressSearch est vrai", () => {
  render(
    <MapView
      config={config}
      addressSearch
      getCoreUrl={() => "https://core.test/v1"}
      getAuthToken={() => "tok"}
    />,
  );
  expect(screen.getByPlaceholderText("Rechercher une adresse…")).toBeInTheDocument();
});

test("sélectionner un résultat de recherche recentre la carte via flyTo", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          { label: "Tulle", lon: 1.764073, lat: 45.267177, score: 0.94, type: "municipality" },
        ],
      }),
    }),
  );
  vi.useFakeTimers({ shouldAdvanceTime: true });
  render(
    <MapView
      config={config}
      addressSearch
      getCoreUrl={() => "https://core.test/v1"}
      getAuthToken={() => "tok"}
    />,
  );
  fireEvent.change(screen.getByPlaceholderText("Rechercher une adresse…"), {
    target: { value: "Tulle" },
  });
  await vi.advanceTimersByTimeAsync(360);
  await screen.findByText("Tulle");
  fireEvent.click(screen.getByText("Tulle"));
  expect(mapInstances[0].flyToArgs).toContainEqual({
    center: [1.764073, 45.267177],
    zoom: 13,
  });
  vi.useRealTimers();
});
```

Ajouter `fireEvent` à l'import existant `@testing-library/react` en tête
de fichier (déjà importe `act, render, screen` ligne 2 — étendre en
`act, fireEvent, render, screen`).

```bash
cd shell && npm run test -- MapView.test.tsx -t "recherche d'adresse"
# attendu : ÉCHEC (prop addressSearch inexistante, contrôle jamais monté)
```

- [ ] **Step 2 : implémenter**

Ajouter l'import en tête de fichier :

```tsx
import { AddressSearchControl } from "./AddressSearchControl";
import { zoomForResultType } from "./addressSearch";
```

Ajouter la prop dans le type de props de `MapView` (à côté de
`interactiveTools?: boolean;`, même commentaire de doctrine) :

```tsx
    // Monte le contrôle de recherche d'adresse (REV-102/GAP-08) : jamais
    // câblé par défaut, comme interactiveTools.
    addressSearch?: boolean;
```

Ajouter le paramètre dans la déstructuration des props de la fonction
`MapView` (à côté de `interactiveTools,`) :

```tsx
    addressSearch,
```

Ajouter le rendu conditionnel, à côté du bloc `{interactiveTools &&
readyMap && (...)}`  existant :

```tsx
      {addressSearch && readyMap && (
        <AddressSearchControl
          getCoreUrl={getCoreUrl}
          getAuthToken={getAuthToken}
          onSelect={(r) =>
            readyMap.flyTo({ center: [r.lon, r.lat], zoom: zoomForResultType(r.type) })
          }
        />
      )}
```

```bash
cd shell && npm run test -- MapView.test.tsx
# attendu : PASS (suite complète du fichier, pas seulement les 3 tests
# ajoutés — vérifier qu'interactiveTools/MapMeasureSketchToolbar
# fonctionnent toujours, piège CLAUDE.md n°4)
```

- [ ] **Step 3 : falsifier le filet de non-montage par défaut**

Remplacer temporairement `{addressSearch && readyMap && (` par
`{readyMap && (` (montage inconditionnel), confirmer que le test « ne
monte pas... sans la prop » échoue, remettre le code correct.

- [ ] **Step 4 : commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): monte le contrôle de recherche d'adresse dans MapView

Nouvelle prop addressSearch?: boolean, même doctrine que
interactiveTools (SP-27) : jamais monté par défaut. La sélection
d'un résultat recentre/zoome la carte via flyTo(), zoom dérivé du
type BAN (zoomForResultType).
EOF
)"
```

---

## Task 10 : sites de montage (`MapEditorPage.tsx`, `mapWidget.tsx`)

**Files:**
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Test: `shell/src/pages/MapEditorPage.test.tsx`
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: prop `addressSearch` de `MapView` (Task 9).

- [ ] **Step 1 : écrire les tests (avant le code)**

`MapEditorPage.test.tsx` ne mocke pas `MapView` (il mocke `maplibre-gl`
directement, ligne 13, exactement comme `MapView.test.tsx`) — le vrai
`MapView` se monte donc réellement, avec le vrai `AddressSearchControl` à
l'intérieur dès que la prop `addressSearch` lui est passée. La façon la
plus fidèle de vérifier que la Tâche 10 câble bien cette prop est donc
d'asserter sur le placeholder réel du contrôle, pas sur une prop
inspectée via un mock. Ajouter, à côté du test existant
`"loads the config and saves edits"` (même fichier, même `renderEditor`
déjà défini plus haut) :

```tsx
test("le contrôle de recherche d'adresse est monté sur l'onglet carte", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A"); // même point de synchronisation que les tests voisins
  expect(screen.getByPlaceholderText("Rechercher une adresse…")).toBeInTheDocument();
});
```

`mapWidget.test.tsx` mocke `MapView` littéralement (lignes 20-75) et rend
déjà `tools:{String(!!interactiveTools)}` dans le texte du
`data-testid="mapview"` — exactement le test
`"la barre mesure/croquis n'est active qu'en dehors du mode édition"`
(lignes 704-721) à répliquer pour `addressSearch`. Modifier d'abord la
signature du mock (lignes 20-45) pour destructurer et exposer aussi
`addressSearch` :

```tsx
      {
        config,
        onViewChange,
        onFeatureClick,
        loadCustomIcon,
        themeColors,
        interactiveTools,
        addressSearch,
      }: {
        config: MapConfig;
        onViewChange?: (v: {
          center: [number, number];
          zoom: number;
          bbox: [number, number, number, number];
        }) => void;
        onFeatureClick?: (record: {
          id: string | number;
          properties: Record<string, unknown>;
          geometry?: unknown;
        }) => void;
        loadCustomIcon?: (iconId: string) => Promise<Blob>;
        themeColors?: unknown;
        interactiveTools?: boolean;
        addressSearch?: boolean;
      },
```

et le texte rendu (ligne 64-66) pour y ajouter `addressSearch` :

```tsx
          layers:{config.layers.length} url:{url} renderAs:{renderAs} paint:{paint} symbology:
          {symbology} themeColors:{JSON.stringify(themeColors ?? null)} tools:
          {String(!!interactiveTools)} search:{String(!!addressSearch)} loader:{typeof loadCustomIcon}
```

Puis ajouter le test, juste après celui de la barre mesure/croquis :

```tsx
test("la recherche d'adresse n'est active qu'en dehors du mode édition", async () => {
  const Map = getWidget("map")!.Component;
  const data = state({
    url: "https://fs/communes/items.json",
    records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
  });
  const { rerender } = render(
    withClient(<Map props={{ dataSourceId: "d" }} ctx={{ mode: "edit", data } as WidgetContext} />),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("search:false");

  rerender(
    withClient(
      <Map props={{ dataSourceId: "d" }} ctx={{ mode: "runtime", data } as WidgetContext} />,
    ),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("search:true");
});
```

```bash
cd shell && npm run test -- MapEditorPage.test.tsx mapWidget.test.tsx
# attendu : ÉCHEC — MapEditorPage.test.tsx : placeholder introuvable
# (addressSearch pas encore câblé) ; mapWidget.test.tsx : "search:false"
# constant (le texte "search:" existe déjà grâce au mock modifié, mais
# addressSearch n'est jamais passé par mapWidget.tsx donc toujours false)
```

- [ ] **Step 2 : implémenter — `MapEditorPage.tsx`**

Sur le `<MapView>` de l'onglet `work` (celui qui a déjà
`interactiveTools`, **pas** celui du bloc `isExportRender`) :

```tsx
                <MapView
                  ref={mapViewRef}
                  config={draft}
                  onViewChange={setView}
                  interactiveTools
                  addressSearch
                  getAuthToken={client.getAuthToken}
                  getCoreUrl={client.getCoreUrl}
                  loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
                />
```

- [ ] **Step 3 : implémenter — `mapWidget.tsx`**

Sur le `<MapView>` du `Component` (celui qui a déjà
`interactiveTools={ctx.mode !== "edit"}`) :

```tsx
            <MapView
              ...
              interactiveTools={ctx.mode !== "edit"}
              addressSearch={ctx.mode !== "edit"}
              ...
            />
```

(reprendre exactement les props déjà présentes sur cette balise,
n'ajouter que `addressSearch={ctx.mode !== "edit"}` à côté de
`interactiveTools`).

```bash
cd shell && npm run test -- MapEditorPage.test.tsx mapWidget.test.tsx
# attendu : PASS
```

- [ ] **Step 4 : falsifier le filet**

Sur `mapWidget.tsx`, remplacer temporairement `addressSearch={ctx.mode
!== "edit"}` par `addressSearch={false}`, confirmer que le test
« la recherche d'adresse n'est active qu'en dehors du mode édition »
échoue (le second `expect` ne trouve plus `"search:true"`), remettre le
code correct.

- [ ] **Step 5 : suite complète shell + commit**

```bash
cd shell && npm run test
```

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx \
  shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): active la recherche d'adresse sur l'éditeur de carte et
le widget carte

MapEditorPage : addressSearch actif sur l'onglet carte (jamais sur
le rendu d'export). mapWidget : addressSearch={ctx.mode !== "edit"},
même prédicat que interactiveTools — actif en aperçu/exécution,
absent pendant l'édition du widget.
EOF
)"
```

---

## Task 11 : E2E `shell/e2e/map-address-search.spec.ts`

**Files:**
- Create: `shell/e2e/map-address-search.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), patron de création d'un
  item carte de `shell/e2e/map-editor.spec.ts:4-24` (dialog « Nouveau » →
  type `map` → titre → `/maps/77`, canvas MapLibre **réel**, pas mocké —
  Chromium a WebGL, `mockCore` ne mocke que le cœur, jamais MapLibre).

**Contrainte découverte en lisant `map-measure-sketch.spec.ts:81-87`
avant d'écrire cette tâche** : ce dépôt n'expose **aucun** global de test
sur `window` pour inspecter l'instance MapLibre réelle depuis Playwright
— décision explicite (« rien n'expose l'instance MapLibre au contexte de
page »), déjà contournée ailleurs par des assertions sur l'UI visible et
le trafic réseau plutôt que sur l'état interne de la carte. Le
recentrage/zoom lui-même (`map.flyTo(...)`, avec les bonnes valeurs) est
donc déjà prouvé de façon fiable au niveau unitaire (Task 9,
`mapInstances[0].flyToArgs` sur le mock MapLibre) — **ne pas** ajouter de
nouveau hook de test exposé en production pour le re-prouver ici, ce
serait le même écart que ce dépôt a déjà choisi d'éviter. Cette spec E2E
prouve à la place ce que Task 9 ne peut pas prouver : le parcours
utilisateur complet contre le vrai composant monté dans la vraie page,
et surtout la garantie de sécurité (§Contexte, aucun appel direct
navigateur→BAN).

- [ ] **Step 1 : écrire le test (avant tout mock dédié)**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

async function createMap(page: import("@playwright/test").Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill(title);
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
}

test("recherche une adresse, sélectionne un résultat, la liste se referme", async ({ page }) => {
  await mockCore(page);
  let searchCalls = 0;
  await page.route("https://core.test/v1/geocoding/search*", async (route) => {
    searchCalls += 1;
    const url = new URL(route.request().url());
    expect(url.searchParams.get("q")).toBe("Tulle");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: [
          {
            label: "Tulle",
            lon: 1.764073,
            lat: 45.267177,
            score: 0.94,
            type: "municipality",
            city: "Tulle",
            postcode: "19000",
          },
        ],
      }),
    });
  });

  await createMap(page, "Ma carte");

  await page.getByPlaceholder("Rechercher une adresse…").fill("Tulle");
  await page.getByRole("button", { name: "Tulle" }).click();

  await expect(page.getByPlaceholder("Rechercher une adresse…")).toHaveValue("Tulle");
  await expect(page.getByRole("list", { name: "Résultats de la recherche d'adresse" })).toHaveCount(
    0,
  );
  expect(searchCalls).toBeGreaterThan(0);
});

test("n'appelle jamais api-adresse.data.gouv.fr directement", async ({ page }) => {
  await mockCore(page);
  let banCalled = false;
  await page.route("https://api-adresse.data.gouv.fr/**", async (route) => {
    banCalled = true;
    await route.fulfill({ status: 200, body: "{}" });
  });
  await page.route("https://core.test/v1/geocoding/search*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ results: [] }),
    });
  });

  await createMap(page, "Ma carte");
  await page.getByPlaceholder("Rechercher une adresse…").fill("Tulle");
  // Laisser le débounce (350 ms) + l'aller-retour réseau se dérouler,
  // sans résultat cliquable à attendre puisque la réponse est vide ici.
  await page.waitForTimeout(600);

  expect(banCalled).toBe(false);
});
```

```bash
cd shell && npm run e2e -- map-address-search.spec.ts
# attendu, si exécuté avant les Tâches 7-10 : ÉCHEC (le placeholder
# "Rechercher une adresse…" n'existe pas encore sur /maps/77). Si les
# Tâches 7-10 sont déjà faites au moment d'exécuter cette tâche : PASS
# direct — dans ce cas, retirer temporairement `addressSearch` du
# montage de MapEditorPage.tsx (Task 10) pour confirmer que ce test
# échoue bien AVANT de le considérer comme un filet valide (cf. Step 2),
# puis remettre.
```

- [ ] **Step 2 : falsifier le filet « jamais d'appel direct à la BAN »**

Modifier temporairement `shell/src/map/addressSearch.ts::searchAddress`
pour construire son URL avec
`https://api-adresse.data.gouv.fr/search/?q=...` en dur au lieu de
`${coreUrl}/geocoding/search?q=...`, confirmer que le test « n'appelle
jamais api-adresse.data.gouv.fr directement » échoue (`banCalled`
devient `true`), remettre le code correct.

- [ ] **Step 3 : suite E2E complète**

```bash
cd shell && npm run e2e
```

Vérifier notamment que `map-editor.spec.ts` et `map-measure-sketch.spec.ts`
passent toujours (piège CLAUDE.md n°4 : la création d'un item carte et la
barre mesure/croquis — même page, mêmes sites de montage — ne doivent
pas avoir régressé après l'ajout d'`addressSearch`).

- [ ] **Step 4 : commit**

```bash
git add shell/e2e/map-address-search.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): couvre la recherche d'adresse sur l'éditeur de carte

Ferme GAP-08/REV-102 (chantier 4.13) : scénario bout-en-bout
(recherche → sélection, sur le vrai composant monté dans /maps/77) et
garde explicite qu'aucune requête ne vise api-adresse.data.gouv.fr
directement depuis le navigateur. Le recentrage/zoom lui-même
(flyTo) est prouvé au niveau unitaire (MapView.test.tsx, Task 9) :
aucun hook de test n'expose l'instance MapLibre réelle au contexte de
page (précédent map-measure-sketch.spec.ts), pas ajouté ici non plus.
EOF
)"
```

---

## Clôture de plan

- [ ] Suite complète cœur : `cd core && uv run pytest` — 0 échec attendu
  hors les échecs déjà documentés comme préexistants et sans rapport
  (cf. `CLAUDE.md` § Suivis non bloquants au moment de l'exécution —
  vérifier lequel est le dernier connu, ne pas supposer que celui cité
  dans ce plan est encore d'actualité).
- [ ] Portes de qualité cœur : `uv run ruff check . && uv run ruff format
  --check .`, `uv run mypy --strict app/auth app/secrets app/analytics
  app/copilot app/admin_tools app/roles` (périmètre inchangé par ce
  plan — `app.geocoding` n'y est pas inclus, cohérent avec
  `app.harvest`/`app.pipelines` qui n'y sont pas non plus), `uv run
  lint-imports`.
- [ ] Suite complète shell : `cd shell && npm run test`, `npm run build`
  (vérifier le seuil de taille de bundle courant), `npm run lint`
  (inclut `check-i18n-coverage.mjs`).
- [ ] E2E complète : `cd shell && npm run e2e`.
- [ ] Diff `openapi.json`/`core-schema.d.ts` revérifié cohérent avec
  l'état final de la branche (pas seulement au moment de la Tâche 6, si
  d'autres tâches ont entre-temps touché une route par erreur — piège
  CLAUDE.md n°1).
- [ ] **Mettre à jour `docs/revue/inventaire-fonctionnalites.jsonl`** avec
  la nouvelle surface REST (`GET /v1/geocoding/search`) et régénérer le
  bilan de fonctionnalités si l'état de `dev` au moment de l'exécution
  porte l'outillage SP-61 (`cd core && PYTHONPATH=. uv run python
  scripts/feature_health_cli.py --repo .. --write`) — vérifier d'abord
  que ces fichiers/scripts existent sur la branche réellement exécutée
  (au moment où cette spec+plan ont été écrits, le worktree utilisé ne
  les portait pas encore : SP-61 n'y était pas fusionné). Mettre aussi à
  jour l'état de GAP-08/REV-102 (ouvert → fermé) dans
  `docs/revue/2026-09-04-analyse-gaps.md`/`2026-09-04-backlog.md`.
- [ ] Ajouter une ligne dans `CLAUDE.md` § Livré (une phrase, patron des
  entrées existantes) — pas de récit long, renvoi vers ce plan/cette
  spec.
- [ ] Revue finale de branche (piège CLAUDE.md n°4) : au minimum,
  vérifier que la barre mesure/croquis (SP-27) fonctionne encore sur les
  deux sites de montage touchés par la Tâche 10.
