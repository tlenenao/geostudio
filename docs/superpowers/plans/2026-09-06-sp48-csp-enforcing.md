# SP-48 — Bascule de la CSP en enforcing : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-72 (`docs/revue/2026-09-04-analyse-gaps.md:226`) pour
3 de ses 4 blocages documentés (`docker-compose.prod.yml:172-188`) — hôtes
WMS/WMTS moissonnés + terrain externe (1), tuilesets 3D externes (2),
incohérence `shell/nginx.conf`/overlay prod (4) — via une allowlist
calculée dynamiquement depuis des données déjà en base
(`HarvestSource.url`, `ConfigRevision.data`, `Extension.module_url`),
poussée à Traefik par un provider fichier qui vient s'ajouter au provider
Docker existant, sans le remplacer. **Le 4e blocage (script-src pour les
widgets d'extension tiers) n'est PAS fermé par ce plan** : `script_hosts`
est calculé (réutilisable immédiatement si la décision produit tombe) mais
jamais câblé sur la directive enforcée — une décision remontée à Tanguy,
documentée avec 4 options à la spec §4, jamais tranchée par ce plan.

**Architecture:** 7 tâches, **majoritairement séquentielles** (contrairement
à SP-45) : Tasks 1→5 construisent puis câblent l'allowlist dynamique dans
cet ordre (extraction pure → agrégation DB → tâche périodique → rendu
Traefik → bascule enforcing) ; Task 6 (garde du blocage 3) ne dépend que
de Task 2 ; Task 7 (fermeture `nginx.conf`) est indépendante et peut
s'exécuter à tout moment. Document source :
`docs/superpowers/specs/2026-09-06-sp48-csp-enforcing-design.md`.

**Tech Stack:** Python/FastAPI + SQLAlchemy + pytest (cœur) ;
procrastinate (`@app.periodic`, exécuté par `worker`) ; Traefik v3.0.4
(provider fichier, à vérifier empiriquement — voir Global Constraints) ;
`docker-compose.yml`/`docker-compose.prod.yml` ; `shell/nginx.conf`.

## Global Constraints

- **TDD / filet-avant-code** systématique : chaque tâche pose son test
  (nouveau, vérifié rouge) avant le code qu'il protège.
- **Falsification obligatoire** (piège CLAUDE.md n°10) : pour chaque test
  ajouté, confirmer qu'il échoue sur le code non corrigé avant de
  committer le fix qui le fait passer.
- Commits **conventional**, un sujet par commit, français (`feat(core):
  …`, `fix(deploy): …`, `test(core): …`, `chore(deploy): …`).
- **Suite complète rejouée avant de clore chaque tâche de code** (piège
  CLAUDE.md n°6) : `cd core && uv run pytest` — jamais un sous-ensemble de
  fichiers.
- **`postgis-test` non tracké par Alembic** : sans objet ici, aucune tâche
  n'ajoute de colonne ni de migration (le module `app.security` ne lit que
  des tables existantes).
- **Vérification empirique obligatoire du comportement réel de Traefik
  avant Task 4** (piège CLAUDE.md n°3) : la spec (§2.4) affirme que
  `traefik:v3.0.4` supporte un provider fichier avec rechargement à chaud
  (`--providers.file.watch=true`) coexistant avec le provider Docker, et
  qu'un routeur peut référencer une middleware `@file` alors que le
  routeur lui-même est défini par labels `@docker` — **aucun conteneur
  Traefik n'a tourné pendant la rédaction de la spec, cette affirmation
  vient de la documentation Traefik, pas d'une vérification empirique
  dans ce dépôt.** Task 4, Étape 1, consiste précisément à vérifier ce
  point contre un vrai conteneur `traefik:v3.0.4` avant d'écrire quoi que
  ce soit dans les fichiers compose définitifs — si le comportement réel
  diverge (ex. un routeur `@docker` ne peut pas référencer une middleware
  `@file`), documenter l'écart et adapter la conception (ex. tout migrer
  vers le provider fichier plutôt que de mélanger les deux) avant de
  continuer.
- **Diff OpenAPI/types TS attendu vide** à la clôture (aucune route,
  aucun schéma de requête/réponse ne change dans ce plan) — à vérifier
  explicitement (piège CLAUDE.md n°1), jamais supposé.
- **Aucune tâche ne dépend de SP-43** (refactorisation structurelle) ni n'y
  touche.
- **Question produit ouverte, à ne jamais trancher en session** : le
  sandboxing des widgets d'extension tiers (blocage 3, spec §4) reste au
  jugement de Tanguy. Task 6 pose un test de garde qui doit **échouer**
  si un futur commit câble `script_hosts` sur `script-src` sans lever
  cette décision — ne jamais retirer ce test pour "débloquer" un
  changement futur sans validation explicite consignée dans le ledger de
  session.

---

## Task 1 : extraction pure d'hôtes (aucun accès DB, aucun réseau)

**Fichiers touchés :** nouveau `core/app/security/__init__.py` ; nouveau
`core/app/security/csp_hosts.py` ; nouveau
`core/tests/test_security_csp_hosts.py`.

### Étape 1 : filet — les 3 fonctions d'extraction, cas simples et pièges

```python
# SPDX-License-Identifier: Apache-2.0
from app.security.csp_hosts import (
    extract_config_external_hosts,
    extract_extension_hosts,
    extract_harvest_hosts,
)


class _FakeHarvestSource:
    def __init__(self, type_: str, url: str) -> None:
        self.type = type_
        self.url = url


def test_extract_harvest_hosts_keeps_only_wms_and_wmts():
    sources = [
        _FakeHarvestSource("wms", "https://tiles.example.com/wms?service=WMS"),
        _FakeHarvestSource("wmts", "https://tiles2.example.org:8443/wmts"),
        _FakeHarvestSource("arcgis", "https://ignored.example.net/rest"),
        _FakeHarvestSource("stac", "https://ignored2.example.net/stac"),
    ]
    assert extract_harvest_hosts(sources) == {
        "https://tiles.example.com",
        "https://tiles2.example.org:8443",
    }


def test_extract_harvest_hosts_empty_list():
    assert extract_harvest_hosts([]) == set()


def test_extract_config_external_hosts_terrain_and_external_tiles3d():
    body = {
        "basemap": {"style": "https://basemap.example/style.json"},
        "view": {"center": [0, 0], "zoom": 1},
        "terrain": {"tilesUrl": "https://dem.example.com/{z}/{x}/{y}.png", "encoding": "terrarium"},
        "layers": [
            {"id": "a", "title": "A", "kind": "tiles3d", "url": "https://3d.example.com/tileset.json"},
            {"id": "b", "title": "B", "kind": "raster", "collectionId": "col-1"},
            {"id": "c", "title": "C", "kind": "vector", "collectionId": "col-2"},
        ],
    }
    assert extract_config_external_hosts(body) == {
        "https://dem.example.com",
        "https://3d.example.com",
    }


def test_extract_config_external_hosts_ignores_internal_proxy_paths():
    # tileset3d/terrain3d convertis : servis par le proxy authentifié du
    # cœur, jamais un hôte externe — une URL relative (ou absente) ne doit
    # jamais produire d'entrée.
    body = {
        "basemap": {"style": "x"},
        "view": {"center": [0, 0], "zoom": 1},
        "layers": [
            {"id": "a", "title": "A", "kind": "tiles3d", "url": "/tileset3d/item-1/tileset.json"},
        ],
    }
    assert extract_config_external_hosts(body) == set()


def test_extract_config_external_hosts_missing_terrain_and_layers():
    assert extract_config_external_hosts({"basemap": {"style": "x"}, "view": {"center": [0, 0], "zoom": 1}}) == set()


class _FakeExtension:
    def __init__(self, module_url: str) -> None:
        self.module_url = module_url


def test_extract_extension_hosts():
    extensions = [
        _FakeExtension("https://cdn.example.com/widgets/gauge.js"),
        _FakeExtension("/extensions/local-widget.js"),  # même origine, ignoré
    ]
    assert extract_extension_hosts(extensions) == {"https://cdn.example.com"}
```

Confirmer rouge (`app.security.csp_hosts` n'existe pas encore) :

```bash
cd core && uv run pytest tests/test_security_csp_hosts.py -v
```

### Étape 2 : implémenter `core/app/security/csp_hosts.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""Extraction pure d'hôtes externes référencés par des documents/tables
déjà en base, pour construire une allowlist CSP calculée (SP-48/GAP-72,
blocages 1/2/3). Aucune fonction ici ne fait d'I/O — la lecture DB vit
dans app.security.service."""

from typing import Protocol, Sequence
from urllib.parse import urlparse

_HARVEST_TILE_TYPES = {"wms", "wmts"}
_TILE_LAYER_KINDS = {"raster", "tiles3d"}


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None  # URL relative (proxy interne) ou schéma non pertinent
    return f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")


class _HarvestSourceLike(Protocol):
    type: str
    url: str


def extract_harvest_hosts(sources: Sequence[_HarvestSourceLike]) -> set[str]:
    hosts = set()
    for source in sources:
        if source.type not in _HARVEST_TILE_TYPES:
            continue
        origin = _origin(source.url)
        if origin:
            hosts.add(origin)
    return hosts


def extract_config_external_hosts(body: dict) -> set[str]:
    hosts = set()
    terrain = body.get("terrain") or {}
    origin = _origin(terrain.get("tilesUrl"))
    if origin:
        hosts.add(origin)
    for layer in body.get("layers") or []:
        if layer.get("kind") not in _TILE_LAYER_KINDS:
            continue
        if layer.get("collectionId"):
            continue  # servi par le cœur (tuiles MVT), jamais un hôte externe
        origin = _origin(layer.get("url") or layer.get("tilesUrl"))
        if origin:
            hosts.add(origin)
    return hosts


class _ExtensionLike(Protocol):
    module_url: str


def extract_extension_hosts(extensions: Sequence[_ExtensionLike]) -> set[str]:
    hosts = set()
    for extension in extensions:
        origin = _origin(extension.module_url)
        if origin:
            hosts.add(origin)
    return hosts
```

Rejouer l'Étape 1 : vert.

Falsifier au moins un cas : commenter temporairement le filtre
`if layer.get("collectionId"): continue`, confirmer que
`test_extract_config_external_hosts_terrain_and_external_tiles3d` échoue
(la couche `b`, interne, apparaîtrait à tort) — puis restaurer.

```bash
cd core && uv run pytest tests/test_security_csp_hosts.py -v
```

### Étape 3 : ajouter `app.security` au contrat de couches

Dans `core/pyproject.toml`, `[[tool.importlinter.contracts]]` `layers`,
insérer `"app.security"` **juste après `"app.compliance"`** (même
rationale : besoin d'importer des modèles de plusieurs modules distincts,
cf. spec §2.2), avec un commentaire expliquant la raison par analogie
explicite avec `app.compliance`.

```bash
cd core && uv run lint-imports
```

(La Task 1 n'importe encore rien depuis `app.harvest`/`app.configs`/
`app.extensions` — ce test de contrat ne fait que vérifier que la nouvelle
entrée ne casse rien d'existant ; Task 2 est celle qui exercera vraiment
la position choisie.)

Commit : `feat(core): extraction pure d'hôtes externes pour l'allowlist CSP (GAP-72)`.

---

## Task 2 : agrégation DB — `compute_csp_allowlist`

**Fichiers touchés :** nouveau `core/app/security/service.py` ; nouveau
`core/tests/test_security_service.py` (marqué `pytest.mark.postgis`,
réutilise la fixture `pg_app`/session existante — même patron que les
tests d'intégration DB déjà présents ailleurs, ex.
`core/tests/test_collections_empty_route.py`).

### Étape 1 : filet — intégration réelle sur les 3 sources

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs.repository import create_config
from app.configs.schemas import BuilderConfig
from app.extensions.models import Extension
from app.harvest.models import HarvestSource
from app.security.service import compute_csp_allowlist


@pytest.mark.postgis
def test_compute_csp_allowlist_aggregates_the_three_sources(pg_session, tenant, user):
    pg_session.add(
        HarvestSource(
            id="src-1",
            tenant_id=tenant.id,
            owner_id=user.id,
            type="wms",
            url="https://tiles.example.com/wms",
        )
    )
    pg_session.add(
        Extension(
            id="acme.gauge",
            tenant_id=tenant.id,
            owner_id=user.id,
            tag="gauge",
            label="Gauge",
            module_url="https://cdn.example.com/gauge.js",
            props=[],
            events=None,
            actions=None,
            default_size={"w": 4, "h": 4},
            permissions={},
        )
    )
    create_config(
        pg_session,
        tenant_id=tenant.id,
        item_id="item-map-1",
        config=BuilderConfig(
            kind="map",
            body={
                "basemap": {"style": "x"},
                "view": {"center": [0, 0], "zoom": 1},
                "terrain": {"tilesUrl": "https://dem.example.com/tiles.png", "encoding": "terrarium"},
                "layers": [],
            },
        ),
    )
    pg_session.commit()

    allowlist = compute_csp_allowlist(pg_session)

    assert "https://tiles.example.com" in allowlist.img_hosts
    assert "https://tiles.example.com" in allowlist.connect_hosts
    assert "https://dem.example.com" in allowlist.img_hosts
    assert "https://cdn.example.com" in allowlist.script_hosts
    # non-régression : un hôte d'extension ne doit jamais apparaître dans
    # img_hosts/connect_hosts, ni un hôte de tuile dans script_hosts.
    assert "https://cdn.example.com" not in allowlist.img_hosts
    assert "https://tiles.example.com" not in allowlist.script_hosts


@pytest.mark.postgis
def test_compute_csp_allowlist_empty_instance_returns_empty_sets(pg_session):
    allowlist = compute_csp_allowlist(pg_session)
    assert allowlist.img_hosts == set()
    assert allowlist.connect_hosts == set()
    assert allowlist.script_hosts == set()
```

Confirmer rouge (`app.security.service` n'existe pas encore) :

```bash
cd core && uv run pytest tests/test_security_service.py -v -m postgis
```

(Reprendre exactement la signature réelle des fixtures `pg_session`/
`tenant`/`user`/`create_config` en usage dans `core/tests/conftest.py` et
les tests voisins de `app.configs`/`app.harvest` — **vérifier les
signatures exactes en tâche d'exécution avant d'écrire ce test au mot
près**, ce plan donne la forme attendue, pas un copier-coller garanti
correct contre les fixtures réelles.)

### Étape 2 : implémenter `core/app/security/service.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""Agrégation DB de l'allowlist CSP (SP-48/GAP-72) — instance entière, pas
par tenant : la CSP protège un domaine public par installation
(GEOSTUDIO_PUBLIC_HOST), il n'existe qu'une seule origine à protéger."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.models import Config, ConfigRevision
from app.extensions.models import Extension
from app.harvest.models import HarvestSource
from app.security.csp_hosts import (
    extract_config_external_hosts,
    extract_extension_hosts,
    extract_harvest_hosts,
)


@dataclass
class CspAllowlist:
    img_hosts: set[str] = field(default_factory=set)
    connect_hosts: set[str] = field(default_factory=set)
    script_hosts: set[str] = field(default_factory=set)


def _latest_map_config_bodies(session: Session) -> list[dict]:
    map_config_ids = session.scalars(select(Config.id).where(Config.kind == "map")).all()
    bodies = []
    for config_id in map_config_ids:
        revision = session.scalars(
            select(ConfigRevision)
            .where(ConfigRevision.config_id == config_id)
            .order_by(ConfigRevision.version.desc())
        ).first()
        if revision is not None:
            bodies.append(revision.data)
    return bodies


def compute_csp_allowlist(session: Session) -> CspAllowlist:
    sources = session.scalars(select(HarvestSource)).all()
    extensions = session.scalars(select(Extension)).all()
    tile_hosts = extract_harvest_hosts(sources)
    for body in _latest_map_config_bodies(session):
        tile_hosts |= extract_config_external_hosts(body)
    return CspAllowlist(
        img_hosts=set(tile_hosts),
        connect_hosts=set(tile_hosts),
        script_hosts=extract_extension_hosts(extensions),
    )
```

Rejouer l'Étape 1 : vert.

Falsifier : commenter temporairement `tile_hosts |= extract_config_external_hosts(body)`,
confirmer que `test_compute_csp_allowlist_aggregates_the_three_sources`
échoue (`https://dem.example.com` absent) — puis restaurer.

### Étape 3 : vérifier le contrat de couches pour de vrai

```bash
cd core && uv run lint-imports
```

`app.security.service` importe désormais `app.configs.models`,
`app.extensions.models`, `app.harvest.models` — la position choisie à la
Task 1 Étape 3 (juste après `app.compliance`) doit suffire sans nouvelle
exemption. Si le contrat échoue, ajuster la position (jamais ajouter une
exemption ponctuelle sans avoir d'abord essayé de déplacer l'entrée, même
raisonnement que le commentaire déjà écrit pour `app.compliance`).

```bash
cd core && uv run pytest
```

Commit : `feat(core): agrège l'allowlist CSP depuis les 3 sources déjà en base (GAP-72)`.

---

## Task 3 : tâche périodique — rendu du fichier de configuration Traefik

**Fichiers touchés :** nouveau `core/app/security/jobs.py` ; nouveau
`core/app/security/traefik_render.py` ; nouveau
`core/tests/test_security_jobs.py`.

### Étape 1 : filet — rendu pur (pas d'écriture disque, pas de DB)

```python
# SPDX-License-Identifier: Apache-2.0
import yaml  # import de test uniquement — jamais en production, cf. spec §2.4

from app.security.service import CspAllowlist
from app.security.traefik_render import render_dynamic_conf


def test_render_dynamic_conf_produces_parseable_yaml_enforce_mode():
    allowlist = CspAllowlist(
        img_hosts={"https://tiles.example.com"},
        connect_hosts={"https://tiles.example.com"},
        script_hosts=set(),
    )
    rendered = render_dynamic_conf(allowlist, mode="enforce")
    parsed = yaml.safe_load(rendered)
    header_name = "Content-Security-Policy"
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert header_name in headers
    assert "https://tiles.example.com" in headers[header_name]
    assert "script-src 'self'" in headers[header_name]  # jamais élargi (blocage 3 non tranché)


def test_render_dynamic_conf_report_only_mode_uses_report_only_header_name():
    allowlist = CspAllowlist()
    rendered = render_dynamic_conf(allowlist, mode="report-only")
    parsed = yaml.safe_load(rendered)
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert "Content-Security-Policy-Report-Only" in headers
    assert "Content-Security-Policy" not in headers


def test_render_dynamic_conf_rejects_unknown_mode():
    import pytest

    with pytest.raises(ValueError):
        render_dynamic_conf(CspAllowlist(), mode="bogus")


def test_render_dynamic_conf_empty_allowlist_still_has_self():
    rendered = render_dynamic_conf(CspAllowlist(), mode="enforce")
    parsed = yaml.safe_load(rendered)
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert "default-src 'self'" in headers["Content-Security-Policy"]
```

Confirmer rouge (`app.security.traefik_render` n'existe pas encore) :

```bash
cd core && uv run pytest tests/test_security_jobs.py -k render -v
```

### Étape 2 : implémenter `core/app/security/traefik_render.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""Génère le fragment de configuration dynamique Traefik (provider
fichier) portant la CSP calculée. Gabarit de chaîne plutôt que pyyaml : ce
module tourne en production (worker), et pyyaml n'est aujourd'hui qu'une
dépendance de développement (core/pyproject.toml, [dependency-groups]) —
faire glisser une dépendance nouvelle vers la production pour ce seul
usage n'a pas été jugé justifié (spec SP-48 §2.4). Les seuls éléments
variables du gabarit sont des origines issues d'urlparse (schéma+hôte+port
optionnel) : elles ne peuvent contenir ni guillemet ni retour à la ligne,
donc aucun risque d'échappement YAML mal formé — vérifié par les tests de
ce fichier via yaml.safe_load (import réservé aux tests)."""

from app.security.service import CspAllowlist

_HEADER_NAMES = {
    "enforce": "Content-Security-Policy",
    "report-only": "Content-Security-Policy-Report-Only",
}


def _build_csp_value(allowlist: CspAllowlist) -> str:
    img = " ".join(sorted({"'self'", "data:", "blob:", *allowlist.img_hosts}))
    connect = " ".join(sorted({"'self'", *allowlist.connect_hosts}))
    # script-src reste 'self', jamais élargi à allowlist.script_hosts tant
    # que le blocage 3 (spec §4) n'est pas tranché par Tanguy — cf. Task 6.
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        f"connect-src {connect}; "
        f"img-src {img}; "
        "worker-src 'self' blob:; "
        "object-src 'none'"
    )


def render_dynamic_conf(allowlist: CspAllowlist, *, mode: str) -> str:
    if mode not in _HEADER_NAMES:
        raise ValueError(f"mode CSP inconnu : {mode!r} (attendu enforce|report-only)")
    header_name = _HEADER_NAMES[mode]
    csp_value = _build_csp_value(allowlist)
    return (
        "http:\n"
        "  middlewares:\n"
        "    csp-dynamic:\n"
        "      headers:\n"
        "        customResponseHeaders:\n"
        f'          "{header_name}": "{csp_value}"\n'
    )
```

Rejouer l'Étape 1 : vert.

Falsifier : dans `_HEADER_NAMES`, inverser temporairement les deux clés
(`"enforce"` pointant vers le nom Report-Only), confirmer que
`test_render_dynamic_conf_produces_parseable_yaml_enforce_mode` échoue —
puis restaurer.

### Étape 3 : filet — la tâche périodique elle-même (écriture disque)

```python
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from app.security.jobs import CSP_DYNAMIC_CONF_PATH, refresh_csp_dynamic_conf_task


@pytest.mark.postgis
def test_refresh_csp_dynamic_conf_task_writes_the_rendered_file(tmp_path, monkeypatch, pg_session):
    target = tmp_path / "dynamic-conf.yml"
    monkeypatch.setenv("CORE_CSP_MODE", "enforce")
    monkeypatch.setattr("app.security.jobs.CSP_DYNAMIC_CONF_PATH", str(target))
    refresh_csp_dynamic_conf_task.run_test(pg_session)  # cf. Étape 4 : forme réelle à vérifier contre le patron des autres tâches @app.periodic du dépôt
    assert target.exists()
    assert "csp-dynamic" in target.read_text()
```

Confirmer rouge.

### Étape 4 : implémenter `core/app/security/jobs.py`

**Reprendre le patron exact d'une tâche `@app.periodic` déjà existante du
dépôt avant d'écrire cette tâche** (ex. `core/app/reports/jobs.py:449-451`,
`sweep_report_schedules_task` — signature, gestion de session, forme
exacte de l'enregistrement `@app.periodic(cron=...)`) : ce plan ne
préjuge pas de la signature procrastinate exacte (nombre d'arguments,
gestion de la session DB dans une tâche périodique — les tâches
existantes ouvrent-elles leur propre session, ou en reçoivent-elles une ?
**à vérifier contre le code réel, pas supposé ici**, piège CLAUDE.md n°3).

```python
# SPDX-License-Identifier: Apache-2.0
import os

from app.jobs import app  # ou le module d'enregistrement procrastinate réel — à vérifier
from app.security.service import compute_csp_allowlist
from app.security.traefik_render import render_dynamic_conf

CSP_DYNAMIC_CONF_PATH = os.environ.get(
    "CSP_DYNAMIC_CONF_PATH", "/csp-dynamic/dynamic-conf.yml"
)


@app.periodic(cron="*/5 * * * *")
def refresh_csp_dynamic_conf_task(timestamp: int) -> None:
    mode = os.environ.get("CORE_CSP_MODE", "report-only")
    with get_session() as session:  # forme exacte à aligner sur les tâches voisines
        allowlist = compute_csp_allowlist(session)
    rendered = render_dynamic_conf(allowlist, mode=mode)
    os.makedirs(os.path.dirname(CSP_DYNAMIC_CONF_PATH), exist_ok=True)
    with open(CSP_DYNAMIC_CONF_PATH, "w") as f:
        f.write(rendered)
```

Rejouer l'Étape 3 : vert.

Falsifier : commenter temporairement l'écriture du fichier, confirmer que
le test échoue (`target.exists()` faux) — puis restaurer.

```bash
cd core && uv run pytest tests/test_security_jobs.py -v
cd core && uv run pytest
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

Commit : `feat(core): tâche périodique de rendu de l'allowlist CSP pour Traefik (GAP-72)`.

---

## Task 4 : câblage Traefik — provider fichier + volume partagé

**Fichiers touchés :** `docker-compose.yml` ; `docker-compose.prod.yml` ;
`.env.example` ; `core/tests/test_deployability.py`.

**Cette tâche commence par une vérification empirique, pas par du code**
(Global Constraints ci-dessus) :

### Étape 0 : vérifier le comportement réel de Traefik (obligatoire avant d'éditer les fichiers compose)

```bash
docker run --rm -d --name traefik-csp-check -p 18080:80 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  traefik:v3.0.4 \
  --providers.docker=true --providers.docker.exposedbydefault=false \
  --providers.file.directory=/etc/traefik/dynamic --providers.file.watch=true \
  --entrypoints.web.address=:80
```

Vérifier au minimum : (a) le conteneur démarre sans erreur avec les deux
providers actifs simultanément ; (b) écrire un fichier
`dynamic-conf.yml` minimal dans un volume monté sur
`/etc/traefik/dynamic`, confirmer qu'il apparaît dans le dashboard/API
Traefik (`--api.insecure=true` + `curl localhost:8080/api/http/middlewares`)
sans redémarrer le conteneur ; (c) qu'une middleware nommée dans ce
fichier (`csp-dynamic@file`) est bien listée comme utilisable. Documenter
le résultat dans le ledger de session — si (a)/(b)/(c) diverge de ce que
la spec suppose, **s'arrêter et adapter la conception avant de continuer
cette tâche**, ne jamais câbler les fichiers compose définitifs contre un
comportement non vérifié.

```bash
docker stop traefik-csp-check
```

### Étape 1 : filet — volume + montages + commande Traefik

```python
def test_csp_dynamic_conf_volume_is_shared_between_worker_and_traefik():
    assert "csp-dynamic-conf" in (load_yaml(BASE).get("volumes") or {})
    worker_volumes = services(BASE)["worker"].get("volumes") or []
    traefik_volumes = services(BASE)["traefik"].get("volumes") or []
    assert any("csp-dynamic-conf" in v for v in worker_volumes)
    assert any("csp-dynamic-conf" in v for v in traefik_volumes)


def test_traefik_command_enables_file_provider_with_watch():
    command = services(BASE)["traefik"]["command"]
    assert "--providers.file.watch=true" in command
    assert any(c.startswith("--providers.file.directory=") for c in command)
```

Confirmer rouge :

```bash
cd core && uv run pytest tests/test_deployability.py -k csp_dynamic -v
```

### Étape 2 : fix — volume + montages + commande, fichier de base

Dans `docker-compose.yml` :
- `volumes:` (racine) : ajouter `csp-dynamic-conf:` aux côtés de
  `pg-data`/`minio-data`/`keycloak-data`.
- Service `worker` : ajouter `volumes: [..., csp-dynamic-conf:/csp-dynamic]`
  (préserver les volumes déjà présents s'il y en a — vérifier avant
  d'écraser).
- Service `traefik` (`command:`) : ajouter
  `--providers.file.directory=/csp-dynamic` et
  `--providers.file.watch=true` ; `volumes:` : ajouter
  `csp-dynamic-conf:/csp-dynamic`.

Rejouer l'Étape 1 : vert.

### Étape 3 : filet + fix — même câblage sur l'overlay prod

`docker-compose.prod.yml` déclare son propre bloc `traefik: command:`
(lignes 261-264 relevées en session) — **ne redéfinit pas `worker`**
(hérite du fichier de base, `worker: image: ...` seulement, `build:
!reset null`) : le volume `csp-dynamic-conf:/csp-dynamic` du fichier de
base s'applique donc déjà à `worker` en prod sans rien ajouter côté
`worker`. Seul `traefik` doit être complété dans l'overlay :

```python
def test_prod_traefik_command_also_enables_file_provider():
    command = services(PROD)["traefik"]["command"]
    assert "--providers.file.watch=true" in command
    assert any(c.startswith("--providers.file.directory=") for c in command)
```

Fix : ajouter les deux mêmes entrées au bloc `command:` de `traefik` dans
`docker-compose.prod.yml`. Vérifier que ce bloc reste `!override` ou
fusionne comme attendu — **la fusion Compose sur les listes `command:`
remplace la liste entière plutôt que de la concaténer** (à confirmer
contre `docker compose config` réel, pas supposé) : si c'est le cas,
**recopier l'intégralité de la commande de base** dans le bloc prod
plutôt que de n'ajouter que les 2 nouvelles entrées, pour ne pas perdre
`--providers.docker=true`/`--entrypoints.web.address=:80` existants
(piège CLAUDE.md n°2 : capacité redéfinie qui écrase silencieusement
l'existant).

```bash
cd core && uv run pytest tests/test_deployability.py -k csp_dynamic -v
```

### Étape 4 : filet + fix — chaque routeur gagne `csp-dynamic@file`

```python
@pytest.mark.parametrize(
    ("compose_path", "router"),
    [
        (BASE, "core"), (BASE, "shell"), (BASE, "seo-static"), (BASE, "seo-bots"),
        (BASE, "martin"), (BASE, "titiler"), (BASE, "grafana"),
        (PROD, "core"), (PROD, "shell"), (PROD, "seo-static"), (PROD, "seo-bots"),
        (PROD, "martin"), (PROD, "titiler"), (PROD, "grafana"), (PROD, "keycloak"),
    ],
)
def test_every_router_carrying_security_headers_also_carries_csp_dynamic(compose_path, router):
    # Chaque routeur qui référence déjà security-headers@docker aujourd'hui
    # doit gagner csp-dynamic@file — même périmètre, pas une nouvelle
    # décision de portée (GAP-72 ne change pas QUI est protégé, seulement
    # COMMENT la CSP est calculée).
    all_labels = {name: _traefik_labels(svc) for name, svc in services(compose_path).items()}
    labels = next(l for l in all_labels.values() if f"traefik.http.routers.{router}.middlewares" in l)
    middlewares = _router_middlewares(labels, router)
    assert "security-headers@docker" in middlewares  # non-régression
    assert "csp-dynamic@file" in middlewares
```

Confirmer rouge (aucun routeur ne référence encore `csp-dynamic@file`).

Fix : ajouter `csp-dynamic@file` à la fin de la liste `middlewares=` de
chacun des 7 routeurs du fichier de base, et des 8 de l'overlay prod
(7 + `keycloak`, prod uniquement — cf. commentaire déjà présent dans
`test_keycloak_router_carries_security_and_rate_limit_middlewares`).

Rejouer : vert.

### Étape 5 : retirer la ligne CSP statique de l'overlay prod

```python
def test_prod_overlay_no_longer_hardcodes_a_static_csp_header():
    labels = _traefik_labels(services(PROD)["core"])
    assert not any(
        "Content-Security-Policy" in k and "customResponseHeaders" in k for k in labels
    ), "la CSP doit venir de csp-dynamic@file, plus d'une valeur statique sur security-headers"
```

Confirmer rouge (la ligne `docker-compose.prod.yml:189` existe encore).

Fix : retirer la ligne
`traefik.http.middlewares.security-headers.headers.customResponseHeaders.Content-Security-Policy-Report-Only=…`
de `docker-compose.prod.yml`, et le bloc de commentaire des 4 blocages
(172-188) — remplacé par un commentaire court renvoyant vers la spec
SP-48 et rappelant que le blocage 3 (script-src) reste ouvert (spec §4),
jamais tranché par ce plan.

Rejouer : vert.

```bash
cd core && uv run pytest
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

### Étape 6 : `.env.example` — `CORE_CSP_MODE`

Ajouter, à côté des autres réglages `CORE_*_MODE` (`CORE_AUTH_MODE`) :

```
# GAP-72/SP-48 : "enforce" (défaut recommandé en production, cf. overlay
# prod) bascule la CSP en Content-Security-Policy (bloquant) ; "report-only"
# repasse en Content-Security-Policy-Report-Only sans redéployer d'image —
# rollback opérateur en cas de faux positif imprévu sur l'allowlist
# calculée. Défaut de ce fichier (base, sans overlay prod) : report-only.
CORE_CSP_MODE=report-only
```

et documenter, dans l'overlay prod ou sa documentation opérateur, que le
défaut recommandé en production est `enforce` (Task 5 en fixe la valeur
par défaut effective pour le déploiement de référence).

```bash
cd core && uv run pytest tests/test_deployability.py -k every_documented_env_var -v
```

(Ce test existant, `test_every_documented_env_var_is_wired_or_declared_inert`,
doit rester vert — `CORE_CSP_MODE` est lu par `refresh_csp_dynamic_conf_task`,
côté `worker` : vérifier qu'il compte comme "câblé" selon la logique de ce
test, sinon l'ajouter à ses exemptions documentées avec la même rigueur que
les entrées déjà présentes.)

Commit : `feat(deploy): provider fichier Traefik pour une CSP calculée dynamiquement (GAP-72)`.

---

## Task 5 : bascule effective — `CORE_CSP_MODE=enforce` en production

**Fichiers touchés :** `docker-compose.prod.yml` ;
`core/tests/test_deployability.py`.

### Étape 1 : filet

```python
def test_prod_overlay_defaults_csp_mode_to_enforce():
    env = services(PROD)["worker"].get("environment") or {}
    assert env.get("CORE_CSP_MODE", "").startswith("${CORE_CSP_MODE:-enforce}") or env.get(
        "CORE_CSP_MODE"
    ) == "enforce"
```

(Adapter la forme exacte de l'assertion à la convention réellement choisie
pour exposer `CORE_CSP_MODE` au service `worker` dans l'overlay prod —
`${CORE_CSP_MODE:-enforce}` si l'on garde un override opérateur possible,
valeur en dur `enforce` sinon ; **choisir une seule forme et la tester
au mot près**, ne pas laisser le test flou.)

Confirmer rouge (l'overlay ne fixe aujourd'hui aucune valeur par défaut à
`enforce`, `CORE_CSP_MODE` n'existe même pas encore dans ce fichier).

### Étape 2 : fix

Dans `docker-compose.prod.yml`, service `worker` (hérité du fichier de
base — vérifier s'il faut un bloc `environment:` dédié dans l'overlay ou
si le fichier de base suffit avec un `.env.prod` positionnant
`CORE_CSP_MODE=enforce`) : fixer le défaut effectif de production à
`enforce`.

Rejouer l'Étape 1 : vert.

### Étape 3 : vérification de bout en bout, empirique

Avec un conteneur Traefik réel (relancer la vérification de la Task 4
Étape 0, cette fois avec le fichier `dynamic-conf.yml` réellement produit
par `refresh_csp_dynamic_conf_task` contre une base de test peuplée d'au
moins une `HarvestSource`, un `MapConfig` avec terrain, une `Extension`) :
confirmer par une requête HTTP réelle que le header
`Content-Security-Policy` (pas `-Report-Only`) est bien renvoyé par
`shell`/`core` derrière Traefik, avec les hôtes attendus dans
`img-src`/`connect-src`, et `script-src 'self'` inchangé. Documenter le
résultat (avant/après) dans le ledger de session — ne jamais clore cette
tâche sur la seule lecture des tests unitaires/deployability, la bascule
CSP réelle sur un vrai conteneur est la seule preuve qui compte ici.

```bash
cd core && uv run pytest
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

Commit : `feat(deploy): bascule la CSP en enforcing en production (GAP-72)`.

---

## Task 6 : garde du blocage 3 — `script_hosts` calculé, jamais enforcé

**Fichiers touchés :** `core/tests/test_security_jobs.py` (test ajouté) ;
`core/tests/test_security_service.py` (test ajouté).

**But** : empêcher qu'un futur commit câble silencieusement
`script_hosts` sur `script-src` sans que la décision produit (spec §4)
ait été explicitement validée par Tanguy — matérialiser la décision
« non tranchée » par un test qui échoue si quelqu'un l'élargit, pas
seulement par un commentaire.

### Étape 1 : test de garde sur le rendu

```python
def test_script_src_never_widened_by_computed_extension_hosts():
    """SP-48/GAP-72 blocage 3 : le sandboxing des widgets d'extension
    tiers est une décision produit non tranchée (spec §4, 4 options
    évaluées, aucune retenue sans accord explicite de Tanguy). Ce test
    échoue intentionnellement si script_hosts est un jour branché sur
    script-src sans qu'on ait d'abord retiré ce test — c'est le signal
    que la décision a été prise ailleurs (ledger de session, CLAUDE.md)
    avant de le faire."""
    allowlist = CspAllowlist(script_hosts={"https://cdn.example.com"})
    rendered = render_dynamic_conf(allowlist, mode="enforce")
    assert "cdn.example.com" not in rendered
    assert "script-src 'self'" in rendered
```

Confirmer que ce test est **déjà vert** avec le code de Task 3 (Task 3
n'a jamais câblé `script_hosts` sur `script-src`) — ce n'est pas un
filet-avant-code classique (rien à corriger), c'est un test de
**non-régression intentionnelle**, à committer séparément pour qu'il
apparaisse comme une décision explicite dans l'historique, pas comme un
sous-produit accidentel de Task 3.

### Étape 2 : test de garde sur le calcul lui-même

```python
@pytest.mark.postgis
def test_compute_csp_allowlist_still_separates_script_hosts_from_tile_hosts(pg_session, tenant, user):
    """Même intention que le test de rendu ci-dessus, à un niveau plus
    bas : si compute_csp_allowlist fusionnait un jour script_hosts dans
    img_hosts/connect_hosts (ou l'inverse), ce test le détecterait même
    si render_dynamic_conf n'était pas encore touché."""
    pg_session.add(
        Extension(
            id="acme.only-script",
            tenant_id=tenant.id,
            owner_id=user.id,
            tag="x",
            label="X",
            module_url="https://script-only.example.com/w.js",
            props=[],
            events=None,
            actions=None,
            default_size={"w": 1, "h": 1},
            permissions={},
        )
    )
    pg_session.commit()
    allowlist = compute_csp_allowlist(pg_session)
    assert allowlist.script_hosts == {"https://script-only.example.com"}
    assert allowlist.img_hosts == set()
    assert allowlist.connect_hosts == set()
```

```bash
cd core && uv run pytest tests/test_security_jobs.py tests/test_security_service.py -v
cd core && uv run pytest
```

Commit : `test(core): garde le blocage 3 (script-src) explicitement non fermé (GAP-72)`.

---

## Task 7 : ferme le blocage 4 — Traefik seule source de CSP

**Fichiers touchés :** `shell/nginx.conf` ; `core/tests/test_deployability.py`
(ou un test dédié côté `shell` si plus approprié — à trancher en tâche
d'exécution selon où vivent déjà les tests qui lisent `nginx.conf`, s'il
en existe).

**Indépendante des Tasks 1-6** — peut s'exécuter à tout moment du plan
(y compris en tout premier, si un exécutant préfère grouper les tâches
"infra pure" avant les tâches "core Python").

### Étape 1 : filet

```python
def test_shell_nginx_conf_no_longer_hardcodes_its_own_csp():
    """SP-48/GAP-72 blocage 4 : shell/nginx.conf portait sa propre valeur
    Content-Security-Policy-Report-Only, reconnue fausse par son propre
    commentaire pour la topologie 'ports publiés directement' du fichier
    de base — retirée plutôt que resynchronisée indéfiniment avec la
    valeur Traefik (spec §3). Traefik (base et prod, cf. Task 4) est
    désormais la seule source de CSP dans toute topologie qui passe par
    lui — la seule documentée par ce dépôt."""
    content = (REPO / "shell/nginx.conf").read_text()
    assert "Content-Security-Policy" not in content
```

Confirmer rouge (la ligne existe aujourd'hui, ligne 14).

### Étape 2 : fix

Retirer la ligne `add_header Content-Security-Policy-Report-Only "…" always;`
de `shell/nginx.conf`, remplacée par un commentaire :

```
# La CSP est désormais portée exclusivement par Traefik (middleware
# csp-dynamic@file, cf. SP-48/GAP-72) — dans toute topologie documentée
# par ce dépôt, shell sert toujours derrière Traefik (11 services par
# défaut, CLAUDE.md §Commandes). Un accès direct au port publié de ce
# conteneur, hors Traefik, ne reçoit aucune CSP : ce n'est pas une
# topologie de production documentée.
```

Rejouer l'Étape 1 : vert.

### Étape 3 : suite E2E shell (non-régression, aucun impact attendu)

```bash
cd shell && npm run e2e
```

(`playwright.config.ts` sert via `vite preview`, qui n'exécute jamais
`nginx.conf` — **vert attendu sans changement de comportement**, cf. spec
§1.d. Rejouer explicitement plutôt que supposer, piège CLAUDE.md n°4.)

Commit : `fix(deploy): retire la CSP dupliquée de shell/nginx.conf, Traefik en devient l'unique source (GAP-72)`.

---

## Clôture de plan

- [ ] **Suite complète finale** (cœur) :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

(`app.security` n'est pas dans le périmètre `mypy --strict` actuel — à
trancher en tâche d'exécution si l'équipe souhaite l'y ajouter ; ce plan
ne le présuppose pas.)

- [ ] **Suite shell** :

```bash
cd shell && npm run test && npm run e2e && npm run build
```

- [ ] **Diff OpenAPI/types TS vide, vérifié explicitement** (piège
  CLAUDE.md n°1) :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json  # attendu : vide
cd ../shell && npm run gen:api-types
git diff shell/src/api/generated/core-schema.d.ts  # attendu : vide
```

- [ ] **`docker compose config` résout sans erreur** avec un `.env`/
  `.env.prod` minimal (base seul, puis base+prod), et
  `services.traefik.command` contient bien les 2 nouveaux flags dans les
  deux résolutions.

- [ ] **Vérification empirique Traefik documentée dans le ledger** (Task 4
  Étape 0 et Task 5 Étape 3) — jamais clore le plan sur la seule lecture
  des tests Python, qui ne peuvent pas prouver le comportement réel d'un
  conteneur Traefik.

- [ ] **Statut du blocage 3** explicitement rappelé dans le ledger de
  clôture : non fermé, 4 options documentées (spec §4), recommandation
  Option A donnée mais non appliquée, décision au jugement de Tanguy.
  Reformuler la question pour lui plutôt que la considérer résolue par ce
  plan.

- [ ] **Mettre à jour `CLAUDE.md`** (`### Livré`) avec une ligne SP-48
  résumant : allowlist CSP calculée depuis 3 sources déjà en base
  (harvest/config/extensions), CSP enforcing en production sur
  img-src/connect-src, `shell/nginx.conf` n'a plus sa propre CSP,
  `CORE_CSP_MODE` en rollback opérateur ; et sous
  `### Suivis et dette non bloquante`, le blocage 3 (script-src / GAP-72
  partiel) comme question produit ouverte, avec pointeur vers spec §4.
