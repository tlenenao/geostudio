# SP-41 — Métadonnées éditables et licence par jeu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une collection peut déclarer une licence (résolue en URI DCAT-AP réelle et en identifiant SPDX pour STAC), un producteur, un contact, une fréquence de mise à jour, une généalogie, une langue, une version et une emprise temporelle ; un item quelconque (map/app/dashboard/…) peut déclarer une licence et une langue ; un bug qui effaçait les mots-clés existants d'un item à chaque ouverture du panneau Éditer est corrigé.

**Architecture:** Nouveau module cœur `app/catalog/` (données statiques, zéro dépendance, placé sous `app.analytics` dans le contrat de couches) fournit les trois catalogues curatés (licences, fréquences, langues) et une route `GET /metadata-catalog`. `Collection` et `Item` gagnent chacun de nouvelles colonnes (migration Alembic unique 0033), câblées dans `patch_collection`/`update_item` et dans les deux exports en lecture seule (`app.dcat`, `app.stac`). Côté shell, `EditCollectionPanel` passe sur des onglets (`ui/kit/Tabs`) pour absorber les nouveaux champs, `MetadataForm` (consommé par `ItemDetailPage` pour tout type d'item) gagne licence + langue, et le bug de mots-clés y est corrigé au passage.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (cœur), React + TanStack Query + Radix UI kit (shell), pytest (+ rdflib/pyshacl pour la conformité DCAT-AP), Vitest.

## Global Constraints

- Docs et messages utilisateur en français ; code/identifiants en anglais (CLAUDE.md).
- Commits conventionnels (`feat(core): …`, `fix(shell): …`), petits, un sujet, suffixés `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` uniquement si l'utilisateur demande un commit — ici chaque tâche committe directement (patron subagent-driven-development).
- TDD systématique : test rouge avant l'implémentation, à chaque tâche.
- Tout nouveau champ texte de `Collection`/`Item` suit la convention `str, default=""` (jamais `str | None = None`) — voir spec §1.1, une chaîne vide signifie « non déclaré » et se distingue proprement d'un champ omis en `PATCH`.
- Tout nouveau champ est **omis des exports DCAT-AP/STAC** quand il vaut `""` (ou `None` pour les dates) — critère de non-régression : une collection qui ne touche à rien de nouveau doit produire un export byte-identique à avant ce plan (spec §7.2).
- Piège n°1 (CLAUDE.md) : régénérer la spec OpenAPI + les types TS dès qu'une route ou un modèle change — fait explicitement en Task 7, diff **non vide** attendu (nouvelle route, nouveaux champs).
- Piège n°5 : tout nouveau champ de `CollectionAdmin`/`Item` doit être lu par le passthrough shell (`getItem`/`getCollection`/`listCollections` dans `shell/src/api/itemClient.ts` sont un passthrough JSON direct, vérifié en Task 7 — pas de reconstruction champ à champ à mettre à jour ailleurs).
- Piège n°6 : relancer la suite E2E complète avant de clore (Task 10).
- Piège n°8 : toute migration Alembic testée dans les deux sens sur une base Postgres réellement non vide (Task 2).
- Piège n°10 : tout polyfill jsdom pour Radix (`hasPointerCapture`, `scrollIntoView`) reste local au fichier de test qui en a besoin, jamais dans `shell/src/test/setup.ts`.
- Spec de référence : `docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md`.

---

## Task 1: Catalogue curaté cœur (`app/catalog/`) + route `GET /metadata-catalog`

**Files:**
- Create: `core/app/catalog/__init__.py` (vide)
- Create: `core/app/catalog/metadata.py`
- Create: `core/app/catalog/schemas.py`
- Create: `core/app/catalog/routes.py`
- Create: `core/tests/test_catalog_metadata.py`
- Create: `core/tests/test_catalog_routes.py`
- Modify: `core/pyproject.toml` (contrat de couches)
- Modify: `core/app/main.py` (montage du routeur)

**Interfaces:**
- Produces (consommé par Task 3, 4, 5, 6) : `app.catalog.metadata.LICENSES: list[LicenseEntry]`, `FREQUENCIES: list[FrequencyEntry]`, `LANGUAGES: list[LanguageEntry]`, `LICENSE_IDS: frozenset[str]`, `FREQUENCY_IDS: frozenset[str]`, `LANGUAGE_IDS: frozenset[str]`, `resolve_license(id: str) -> LicenseEntry | None`, `resolve_frequency(id: str) -> FrequencyEntry | None`, `resolve_language(id: str) -> LanguageEntry`, `validate_license_id(value: str | None) -> str | None`, `validate_frequency_id(value: str | None) -> str | None`, `validate_language_id(value: str | None) -> str | None` (les trois `validate_*` lèvent `ValueError` sur un id inconnu, sinon renvoient `value` inchangé — pensés pour être appelés depuis un `@field_validator` pydantic).
- Route produite : `GET /metadata-catalog` (authentifié, aucun privilège requis), réponse `{"licenses": [...], "frequencies": [...], "languages": [...]}`.

- [ ] **Step 1: Écrire `app/catalog/metadata.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Catalogues curatés pour les métadonnées de Collection/Item (chantier 4.9,
docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md §2).
Zéro dépendance interne (même discipline que app.roles.privileges) : ce
module est placé tout en bas du contrat de couches (core/pyproject.toml),
importable par app.collections, app.items, app.dcat et app.stac sans
exemption."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LicenseEntry:
    id: str
    label: str
    dcat_uri: str | None  # None = pas d'URI DCAT-AP dédiée (proprietary/other)
    spdx_id: str


LICENSES: list[LicenseEntry] = [
    LicenseEntry(
        id="etalab-2.0",
        label="Licence Ouverte / Open Licence 2.0 (Etalab)",
        dcat_uri="https://spdx.org/licenses/etalab-2.0.html",
        spdx_id="etalab-2.0",
    ),
    LicenseEntry(
        id="cc0-1.0",
        label="CC0 1.0 Universal",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC0",
        spdx_id="CC0-1.0",
    ),
    LicenseEntry(
        id="cc-by-4.0",
        label="Creative Commons Attribution 4.0",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC_BY",
        spdx_id="CC-BY-4.0",
    ),
    LicenseEntry(
        id="cc-by-sa-4.0",
        label="Creative Commons Attribution-ShareAlike 4.0",
        dcat_uri="http://publications.europa.eu/resource/authority/licence/CC_BY_SA",
        spdx_id="CC-BY-SA-4.0",
    ),
    LicenseEntry(
        id="odbl-1.0",
        label="Open Database License 1.0",
        dcat_uri="https://spdx.org/licenses/ODbL-1.0.html",
        spdx_id="ODbL-1.0",
    ),
    LicenseEntry(
        id="proprietary",
        label="Propriétaire (aucune réutilisation)",
        dcat_uri=None,
        spdx_id="proprietary",
    ),
    LicenseEntry(id="other", label="Autre (URI à saisir)", dcat_uri=None, spdx_id="other"),
]

LICENSE_IDS: frozenset[str] = frozenset(entry.id for entry in LICENSES)
_LICENSES_BY_ID: dict[str, LicenseEntry] = {entry.id: entry for entry in LICENSES}


def resolve_license(license_id: str) -> LicenseEntry | None:
    return _LICENSES_BY_ID.get(license_id)


def validate_license_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in LICENSE_IDS:
        raise ValueError(f"unknown license id: {value!r}")
    return value


@dataclass(frozen=True)
class FrequencyEntry:
    id: str
    label: str
    mdr_freq_uri: str


FREQUENCIES: list[FrequencyEntry] = [
    FrequencyEntry(
        id="continuous",
        label="Continue",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/CONT",
    ),
    FrequencyEntry(
        id="daily",
        label="Quotidienne",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/DAILY",
    ),
    FrequencyEntry(
        id="weekly",
        label="Hebdomadaire",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/WEEKLY",
    ),
    FrequencyEntry(
        id="monthly",
        label="Mensuelle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/MONTHLY",
    ),
    FrequencyEntry(
        id="quarterly",
        label="Trimestrielle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/QUARTERLY",
    ),
    FrequencyEntry(
        id="annual",
        label="Annuelle",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/ANNUAL",
    ),
    FrequencyEntry(
        id="irregular",
        label="Irrégulière",
        mdr_freq_uri="http://publications.europa.eu/resource/authority/frequency/IRREG",
    ),
]

FREQUENCY_IDS: frozenset[str] = frozenset(entry.id for entry in FREQUENCIES)
_FREQUENCIES_BY_ID: dict[str, FrequencyEntry] = {entry.id: entry for entry in FREQUENCIES}


def resolve_frequency(frequency_id: str) -> FrequencyEntry | None:
    return _FREQUENCIES_BY_ID.get(frequency_id)


def validate_frequency_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in FREQUENCY_IDS:
        raise ValueError(f"unknown update_frequency id: {value!r}")
    return value


@dataclass(frozen=True)
class LanguageEntry:
    id: str
    label: str
    alpha3: str  # code de la table d'autorité UE (majuscules)


LANGUAGES: list[LanguageEntry] = [
    LanguageEntry("fr", "Français", "FRA"),
    LanguageEntry("en", "Anglais", "ENG"),
    LanguageEntry("de", "Allemand", "DEU"),
    LanguageEntry("es", "Espagnol", "SPA"),
    LanguageEntry("it", "Italien", "ITA"),
]

LANGUAGE_IDS: frozenset[str] = frozenset(entry.id for entry in LANGUAGES)
_LANGUAGES_BY_ID: dict[str, LanguageEntry] = {entry.id: entry for entry in LANGUAGES}


def resolve_language(language_id: str) -> LanguageEntry:
    # Toujours résolu : language n'est jamais vide (défaut "fr", modèle
    # Collection/Item) et les seules valeurs acceptées en écriture sont
    # celles de LANGUAGE_IDS (validate_language_id).
    return _LANGUAGES_BY_ID[language_id]


def validate_language_id(value: str | None) -> str | None:
    if value is not None and value not in LANGUAGE_IDS:
        raise ValueError(f"unknown language id: {value!r}")
    return value
```

- [ ] **Step 2: Écrire le test `core/tests/test_catalog_metadata.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.catalog import metadata as m


def test_license_ids_match_the_curated_list():
    assert m.LICENSE_IDS == {
        "etalab-2.0",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "odbl-1.0",
        "proprietary",
        "other",
    }


def test_frequency_ids_match_the_curated_list():
    assert m.FREQUENCY_IDS == {
        "continuous",
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "annual",
        "irregular",
    }


def test_language_ids_match_the_curated_list():
    assert m.LANGUAGE_IDS == {"fr", "en", "de", "es", "it"}


def test_resolve_license_returns_entry_with_dcat_and_spdx_ids():
    entry = m.resolve_license("etalab-2.0")
    assert entry is not None
    assert entry.dcat_uri == "https://spdx.org/licenses/etalab-2.0.html"
    assert entry.spdx_id == "etalab-2.0"


def test_resolve_license_unknown_id_returns_none():
    assert m.resolve_license("bogus") is None


def test_resolve_frequency_unknown_id_returns_none():
    assert m.resolve_frequency("bogus") is None


def test_resolve_language_is_always_resolvable_for_a_valid_id():
    assert m.resolve_language("fr").alpha3 == "FRA"


def test_validate_license_id_accepts_empty_string():
    assert m.validate_license_id("") == ""


def test_validate_license_id_accepts_none():
    assert m.validate_license_id(None) is None


def test_validate_license_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown license id"):
        m.validate_license_id("bogus")


def test_validate_frequency_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown update_frequency id"):
        m.validate_frequency_id("bogus")


def test_validate_language_id_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown language id"):
        m.validate_language_id("bogus")


def test_validate_language_id_rejects_empty_string():
    # Contrairement à license/frequency, "" n'est jamais un id de langue
    # valide : language a toujours une vraie valeur (défaut "fr").
    with pytest.raises(ValueError, match="unknown language id"):
        m.validate_language_id("")
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils passent (le module vient d'être écrit, pas de rouge/vert ici — code et test écrits ensemble par exception, catalogue de données pures sans logique à isoler)**

Run: `cd core && uv run pytest tests/test_catalog_metadata.py -v`
Expected: 13 passed

- [ ] **Step 4: Écrire `app/catalog/schemas.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class LicenseCatalogEntry(BaseModel):
    id: str
    label: str
    dcatUri: str | None
    spdxId: str


class FrequencyCatalogEntry(BaseModel):
    id: str
    label: str


class LanguageCatalogEntry(BaseModel):
    id: str
    label: str


class MetadataCatalog(BaseModel):
    licenses: list[LicenseCatalogEntry]
    frequencies: list[FrequencyCatalogEntry]
    languages: list[LanguageCatalogEntry]
```

- [ ] **Step 5: Écrire `app/catalog/routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends

from app.auth.dependency import get_current_user
from app.catalog import metadata
from app.catalog.schemas import (
    FrequencyCatalogEntry,
    LanguageCatalogEntry,
    LicenseCatalogEntry,
    MetadataCatalog,
)
from app.users.models import User

router = APIRouter()


@router.get("/metadata-catalog", response_model=MetadataCatalog)
def get_metadata_catalog(user: User = Depends(get_current_user)) -> MetadataCatalog:
    return MetadataCatalog(
        licenses=[
            LicenseCatalogEntry(id=e.id, label=e.label, dcatUri=e.dcat_uri, spdxId=e.spdx_id)
            for e in metadata.LICENSES
        ],
        frequencies=[
            FrequencyCatalogEntry(id=e.id, label=e.label) for e in metadata.FREQUENCIES
        ],
        languages=[LanguageCatalogEntry(id=e.id, label=e.label) for e in metadata.LANGUAGES],
    )
```

- [ ] **Step 6: Ajouter `app.catalog` au contrat de couches**

Modify `core/pyproject.toml` — dans `[[tool.importlinter.contracts]]` (name = "layered architecture"), le tableau `layers` se termine par :

```toml
    "app.search",
    "app.analytics",
]
```

Remplacer par :

```toml
    "app.search",
    "app.analytics",
    "app.catalog",
]
```

- [ ] **Step 7: Monter le routeur dans `app/main.py`**

Dans `core/app/main.py`, l'import `from app.auth import routes as auth_routes` (ligne 17) est suivi d'autres imports puis de `from app.collections import routes as collections_routes` (ligne 31). Ajouter juste après la ligne `from app.auth import routes as auth_routes` :

```python
from app.catalog import routes as catalog_routes
```

Puis, dans le bloc `app.include_router(...)`, juste après `app.include_router(collections_routes.router)` (ligne 270), ajouter :

```python
    app.include_router(catalog_routes.router)
```

- [ ] **Step 8: Écrire le test `core/tests/test_catalog_routes.py` (rouge avant le montage — vérifier d'abord qu'il échoue si le Step 7 n'était pas fait, en le lançant maintenant qu'il l'est)**

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        setup_session.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    test_client = TestClient(app)
    yield test_client
    engine.dispose()


def test_metadata_catalog_lists_all_three_families(client):
    res = client.get("/metadata-catalog")
    assert res.status_code == 200
    body = res.json()
    license_ids = {e["id"] for e in body["licenses"]}
    assert license_ids == {
        "etalab-2.0",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "odbl-1.0",
        "proprietary",
        "other",
    }
    assert {e["id"] for e in body["frequencies"]} == {
        "continuous",
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "annual",
        "irregular",
    }
    assert {e["id"] for e in body["languages"]} == {"fr", "en", "de", "es", "it"}


def test_metadata_catalog_license_carries_dcat_and_spdx_ids(client):
    res = client.get("/metadata-catalog")
    etalab = next(e for e in res.json()["licenses"] if e["id"] == "etalab-2.0")
    assert etalab["dcatUri"] == "https://spdx.org/licenses/etalab-2.0.html"
    assert etalab["spdxId"] == "etalab-2.0"


def test_metadata_catalog_requires_authentication():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app)
    res = test_client.get("/metadata-catalog")
    assert res.status_code == 401
    engine.dispose()
```

Run: `cd core && uv run pytest tests/test_catalog_routes.py -v`
Expected: 3 passed

- [ ] **Step 9: Vérifier le contrat de couches**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` (vérifié contre une exécution réelle avant d'écrire ce plan — un seul contrat `[[tool.importlinter.contracts]]` existe dans ce dépôt, nommé « layered architecture » ; le « 30 entrées » de CLAUDE.md compte la longueur de sa liste `layers`, pas un nombre de contrats. Si le message diffère, le lire en entier avant de continuer.)

- [ ] **Step 10: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/catalog core/app/main.py core/pyproject.toml core/tests/test_catalog_metadata.py core/tests/test_catalog_routes.py
git commit -m "feat(core): catalogue curaté licences/fréquences/langues (SP-41)"
```

---

## Task 2: Modèle + migration Alembic (`Collection` + `Item`)

**Files:**
- Modify: `core/app/collections/models.py`
- Modify: `core/app/items/models.py`
- Create: `core/alembic/versions/0033_metadata.py`
- Create: `core/tests/test_metadata_migration_alembic.py`

**Interfaces:**
- Consumes: rien (modèles purs).
- Produces (consommé par Task 3, 4, 5, 6) : `Collection.license: str`, `.license_uri: str`, `.producer: str`, `.contact: str`, `.update_frequency: str`, `.lineage: str`, `.language: str`, `.version: str`, `.temporal_start: date | None`, `.temporal_end: date | None` ; `Item.license: str`, `.language: str`.

- [ ] **Step 1: Modifier `core/app/collections/models.py`**

L'import en tête de fichier :

```python
from datetime import UTC, datetime
```

devient :

```python
from datetime import UTC, date, datetime
```

et l'import SQLAlchemy :

```python
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
```

devient :

```python
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
```

Puis, juste avant `created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)`, ajouter (après la ligne `attachment_fields`) :

```python
    # Métadonnées ouvertes (chantier 4.9, docs/superpowers/specs/
    # 2026-09-04-sp41-metadonnees-licence-design.md §1.1). Convention
    # str/default="" (pas None) : un PATCH ne peut jamais distinguer un champ
    # omis d'un champ explicitement remis à None, donc "" porte le sens
    # "non déclaré" partout ici, cohérent avec description ci-dessus.
    license: Mapped[str] = mapped_column(String, default="", nullable=False)
    license_uri: Mapped[str] = mapped_column(String, default="", nullable=False)
    producer: Mapped[str] = mapped_column(String, default="", nullable=False)
    contact: Mapped[str] = mapped_column(String, default="", nullable=False)
    update_frequency: Mapped[str] = mapped_column(String, default="", nullable=False)
    lineage: Mapped[str] = mapped_column(String, default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="fr", nullable=False)
    version: Mapped[str] = mapped_column(String, default="", nullable=False)
    temporal_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    temporal_end: Mapped[date | None] = mapped_column(Date, nullable=True)
```

- [ ] **Step 2: Modifier `core/app/items/models.py`**

Juste avant `created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)`, ajouter (après la ligne `is_public`) :

```python
    # Métadonnées ouvertes (chantier 4.9, sous-ensemble réduit à license+
    # language — cf. spec §1.2). Même convention str/default="" que
    # Collection.
    license: Mapped[str] = mapped_column(String, default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="fr", nullable=False)
```

- [ ] **Step 3: Écrire la migration `core/alembic/versions/0033_metadata.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Métadonnées ouvertes sur Collection (licence, producteur, contact,
fréquence, généalogie, langue, version, emprise temporelle) et sur Item
(licence, langue) — chantier 4.9,
docs/superpowers/specs/2026-09-04-sp41-metadonnees-licence-design.md

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("license", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("license_uri", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("producer", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("contact", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections",
        sa.Column("update_frequency", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "collections", sa.Column("lineage", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "collections", sa.Column("language", sa.String(), nullable=False, server_default="fr")
    )
    op.add_column(
        "collections", sa.Column("version", sa.String(), nullable=False, server_default="")
    )
    op.add_column("collections", sa.Column("temporal_start", sa.Date(), nullable=True))
    op.add_column("collections", sa.Column("temporal_end", sa.Date(), nullable=True))
    op.add_column("items", sa.Column("license", sa.String(), nullable=False, server_default=""))
    op.add_column(
        "items", sa.Column("language", sa.String(), nullable=False, server_default="fr")
    )


def downgrade() -> None:
    op.drop_column("items", "language")
    op.drop_column("items", "license")
    op.drop_column("collections", "temporal_end")
    op.drop_column("collections", "temporal_start")
    op.drop_column("collections", "version")
    op.drop_column("collections", "language")
    op.drop_column("collections", "lineage")
    op.drop_column("collections", "update_frequency")
    op.drop_column("collections", "contact")
    op.drop_column("collections", "producer")
    op.drop_column("collections", "license_uri")
    op.drop_column("collections", "license")
```

- [ ] **Step 4: Vérifier que la migration s'applique sur base vide (SQLite)**

Run: `cd core && uv run pytest tests/test_collections_routes.py tests/test_items_routes.py -q`
Expected: tous verts (ces suites appellent `init_db(engine)` = `Base.metadata.create_all()`, pas `alembic upgrade` — ce Step vérifie seulement que les nouvelles colonnes du modèle ne cassent pas la création de schéma à froid ; le test réel de la migration elle-même est le Step suivant).

- [ ] **Step 5: Écrire le test de migration réelle `core/tests/test_metadata_migration_alembic.py` (piège n°8 — base Postgres non vide, upgrade/downgrade/upgrade)**

```python
# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration Alembic 0033 (upgrade/downgrade/upgrade) sur
une base Postgres non vide — piège n°8 (CLAUDE.md). Patron identique à
test_attachments_migration_alembic.py (SP-40) : base jetable créée et
détruite par ce test, jamais le schéma partagé postgis-test."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"sp41_migration_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    throwaway_url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", base_url)
    throwaway_engine = sa.create_engine(throwaway_url, isolation_level="AUTOCOMMIT")
    with throwaway_engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    throwaway_engine.dispose()
    try:
        yield throwaway_url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def test_migration_0033_upgrades_and_downgrades_on_a_real_non_empty_base(
    throwaway_database_url,
):
    # Config() SANS chemin de fichier ini : cf. test_attachments_migration_alembic.py
    # (SP-40) pour l'explication complète (fileConfig désactiverait les
    # loggers d'autres modules cœur pour toute la session pytest).
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        # 0032 : juste avant 0033, pour insérer des lignes collections/items
        # RÉELLES avant que la migration testée ne s'applique.
        command.upgrade(alembic_cfg, "0032")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'Tenant', now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) "
                    "VALUES ('r1', 't1', 'Admin', 'admin', true, '[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, "
                    "last_name, is_admin, role_id, created_at, updated_at) "
                    "VALUES ('u1', 't1', 'sub1', 'alice', '', '', true, 'r1', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "description, pk_column, is_public, editable, attachment_fields, "
                    "created_at, updated_at) "
                    "VALUES ('col1', 't1', 'u1', 'col1', 'Col 1', '', 'id', false, true, "
                    "'[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, "
                    "abstract, keywords, is_published, is_public, created_at, updated_at) "
                    "VALUES ('item1', 't1', 'u1', 'map', 'Item 1', '', '[]', false, false, "
                    "now(), now())"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            for name in (
                "license",
                "license_uri",
                "producer",
                "contact",
                "update_frequency",
                "lineage",
                "language",
                "version",
                "temporal_start",
                "temporal_end",
            ):
                assert name in col_columns
            item_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'items'"
                    )
                )
            }
            assert "license" in item_columns
            assert "language" in item_columns
            # La ligne insérée AVANT 0033 a bien été backfillée par les
            # server_default de la migration, pas laissée NULL/en échec.
            col_row = conn.execute(
                sa.text(
                    "SELECT license, language, temporal_start FROM collections "
                    "WHERE id = 'col1'"
                )
            ).one()
            assert col_row == ("", "fr", None)
            item_row = conn.execute(
                sa.text("SELECT license, language FROM items WHERE id = 'item1'")
            ).one()
            assert item_row == ("", "fr")
        engine.dispose()

        command.downgrade(alembic_cfg, "-1")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            assert "license" not in col_columns
            assert "temporal_start" not in col_columns
            item_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'items'"
                    )
                )
            }
            assert "license" not in item_columns
            # Les lignes survivent au downgrade (seules les colonnes ajoutées
            # par 0033 sont retirées).
            assert conn.execute(
                sa.text("SELECT 1 FROM collections WHERE id = 'col1'")
            ).scalar() == 1
            assert conn.execute(
                sa.text("SELECT 1 FROM items WHERE id = 'item1'")
            ).scalar() == 1
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_row = conn.execute(
                sa.text("SELECT license, language FROM collections WHERE id = 'col1'")
            ).one()
            assert col_row == ("", "fr")
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
```

- [ ] **Step 6: Lancer le test de migration (nécessite `CORE_TEST_DATABASE_URL` pointé vers un conteneur `postgis-test` réel — skippé sinon, cf. CLAUDE.md)**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/postgres uv run pytest tests/test_metadata_migration_alembic.py -v -m postgis`
Expected: 1 passed (ou `1 skipped` si aucun conteneur `postgis-test` n'est disponible dans cet environnement — dans ce cas, documenter explicitement le skip dans le rapport de tâche, ne pas prétendre la migration vérifiée).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/collections/models.py core/app/items/models.py core/alembic/versions/0033_metadata.py core/tests/test_metadata_migration_alembic.py
git commit -m "feat(core): colonnes de métadonnées ouvertes sur Collection et Item (SP-41)"
```

---

## Task 3: `CollectionPatch` + `patch_collection` + `_collection_json`

**Files:**
- Modify: `core/app/collections/schemas.py`
- Modify: `core/app/collections/routes.py`
- Modify: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes: `app.catalog.metadata.{validate_license_id, validate_frequency_id, validate_language_id}` (Task 1), `Collection.{license,license_uri,producer,contact,update_frequency,lineage,language,version,temporal_start,temporal_end}` (Task 2).
- Produces (consommé par Task 7) : `_collection_json()` renvoie désormais aussi `license`, `licenseUri`, `producer`, `contact`, `updateFrequency`, `lineage`, `language`, `version`, `temporalStart` (`YYYY-MM-DD` ou `null`), `temporalEnd` (idem).

- [ ] **Step 1: Écrire les tests rouges dans `core/tests/test_collections_routes.py` (ajoutés après `test_register_collection_defaults_attachment_fields_to_empty`)**

```python
def test_register_collection_defaults_open_metadata_to_empty(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    res = client.post("/collections", json={"tableName": "incidents"})
    body = res.json()
    assert body["license"] == ""
    assert body["licenseUri"] == ""
    assert body["producer"] == ""
    assert body["contact"] == ""
    assert body["updateFrequency"] == ""
    assert body["lineage"] == ""
    assert body["language"] == "fr"
    assert body["version"] == ""
    assert body["temporalStart"] is None
    assert body["temporalEnd"] is None


def test_patch_collection_declares_open_metadata(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents",
        json={
            "license": "etalab-2.0",
            "producer": "Ma Régie",
            "contact": "contact@example.org",
            "updateFrequency": "monthly",
            "lineage": "Relevé terrain 2026",
            "language": "en",
            "version": "1.0",
            "temporalStart": "2020-01-01",
            "temporalEnd": "2026-12-31",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["license"] == "etalab-2.0"
    assert body["producer"] == "Ma Régie"
    assert body["contact"] == "contact@example.org"
    assert body["updateFrequency"] == "monthly"
    assert body["lineage"] == "Relevé terrain 2026"
    assert body["language"] == "en"
    assert body["version"] == "1.0"
    assert body["temporalStart"] == "2020-01-01"
    assert body["temporalEnd"] == "2026-12-31"

    get_res = client.get("/collections/incidents")
    assert get_res.json()["license"] == "etalab-2.0"


def test_patch_collection_with_other_license_requires_uri(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents",
        json={"license": "other", "licenseUri": "https://example.org/my-license"},
    )
    assert res.status_code == 200
    assert res.json()["licenseUri"] == "https://example.org/my-license"


def test_patch_collection_rejects_unknown_license(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    res = client.patch("/collections/incidents", json={"license": "bogus"})
    assert res.status_code == 422


def test_patch_collection_rejects_unknown_language(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    res = client.patch("/collections/incidents", json={"language": "bogus"})
    assert res.status_code == 422


def test_patch_collection_without_open_metadata_leaves_it_unchanged(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch("/collections/incidents", json={"license": "etalab-2.0"})

    res = client.patch("/collections/incidents", json={"title": "Nouveau titre"})
    assert res.status_code == 200
    assert res.json()["license"] == "etalab-2.0"
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_collections_routes.py -k "open_metadata or unknown_license or unknown_language" -v`
Expected: FAIL (`KeyError: 'license'` ou 422 non levé — le schéma/la route ne connaissent pas encore ces champs)

- [ ] **Step 3: Modifier `core/app/collections/schemas.py`**

L'import en tête de fichier :

```python
from typing import Literal

from pydantic import BaseModel, Field, field_validator
```

devient :

```python
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.catalog.metadata import validate_frequency_id, validate_language_id, validate_license_id
```

Puis `class CollectionPatch` devient :

```python
class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    isPublic: bool | None = None
    editable: bool | None = None
    attachmentFields: list[AttachmentFieldSpec] | None = None
    license: str | None = None
    licenseUri: str | None = None
    producer: str | None = None
    contact: str | None = None
    updateFrequency: str | None = None
    lineage: str | None = None
    language: str | None = None
    version: str | None = None
    temporalStart: date | None = None
    temporalEnd: date | None = None

    @field_validator("license")
    @classmethod
    def _validate_license(cls, v: str | None) -> str | None:
        return validate_license_id(v)

    @field_validator("updateFrequency")
    @classmethod
    def _validate_update_frequency(cls, v: str | None) -> str | None:
        return validate_frequency_id(v)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str | None) -> str | None:
        return validate_language_id(v)
```

- [ ] **Step 4: Modifier `_collection_json` dans `core/app/collections/routes.py`**

```python
def _collection_json(col, permissions, owner: str | None = None) -> dict:
    return {
        "id": col.id,
        "title": col.title,
        "description": col.description,
        "tableName": col.table_name,
        "isPublic": col.is_public,
        "editable": col.editable,
        "geometryType": col.geometry_type,
        "srid": col.srid,
        "pkColumn": col.pk_column,
        "permissions": permissions.model_dump(),
        "featureCount": col.feature_count,
        "owner": owner,
        "attachmentFields": col.attachment_fields,
        "license": col.license,
        "licenseUri": col.license_uri,
        "producer": col.producer,
        "contact": col.contact,
        "updateFrequency": col.update_frequency,
        "lineage": col.lineage,
        "language": col.language,
        "version": col.version,
        "temporalStart": col.temporal_start.isoformat() if col.temporal_start else None,
        "temporalEnd": col.temporal_end.isoformat() if col.temporal_end else None,
    }
```

- [ ] **Step 5: Étendre la boucle de `patch_collection` dans `core/app/collections/routes.py`**

```python
    for attr, value in (
        ("title", body.title),
        ("description", body.description),
        ("is_public", body.isPublic),
        ("editable", body.editable),
        ("license", body.license),
        ("license_uri", body.licenseUri),
        ("producer", body.producer),
        ("contact", body.contact),
        ("update_frequency", body.updateFrequency),
        ("lineage", body.lineage),
        ("language", body.language),
        ("version", body.version),
        ("temporal_start", body.temporalStart),
        ("temporal_end", body.temporalEnd),
    ):
        if value is not None:
            setattr(col, attr, value)
```

(remplace la boucle existante à 4 entrées ; le reste de la fonction, y compris le bloc `attachmentFields` juste après, est inchangé.)

- [ ] **Step 6: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: tous verts (ancien + nouveaux tests)

- [ ] **Step 7: Portes de qualité**

Run: `cd core && uv run ruff check app/collections && uv run ruff format --check app/collections && uv run lint-imports`
Expected: propre (0 erreur) — `lint-imports` confirme que `app.collections -> app.catalog.metadata` est une arête autorisée (collections au-dessus de catalog dans le contrat).

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/collections/schemas.py core/app/collections/routes.py core/tests/test_collections_routes.py
git commit -m "feat(core): PATCH /collections/{id} déclare les métadonnées ouvertes (SP-41)"
```

---

## Task 4: `ItemUpdatePatch` + `update_item` + `_to_read`

**Files:**
- Modify: `core/app/items/schemas.py`
- Modify: `core/app/items/repository.py`
- Modify: `core/app/items/routes.py`
- Modify: `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes: `app.catalog.metadata.{validate_license_id, validate_language_id}` (Task 1), `Item.{license,language}` (Task 2).
- Produces (consommé par Task 7) : `ItemRead.license: str`, `.language: str` ; `repo.update_item(..., license: str | None = None, language: str | None = None)`.

- [ ] **Step 1: Écrire les tests rouges dans `core/tests/test_items_routes.py`**

```python
def test_get_item_defaults_license_and_language(client):
    item_id = _seed_item(client)
    body = client.get(f"/items/{item_id}").json()
    assert body["license"] == ""
    assert body["language"] == "fr"


def test_patch_item_updates_license_and_language(client):
    item_id = _seed_item(client)
    response = client.patch(
        f"/items/{item_id}", json={"license": "cc-by-4.0", "language": "en"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["license"] == "cc-by-4.0"
    assert body["language"] == "en"

    get_body = client.get(f"/items/{item_id}").json()
    assert get_body["license"] == "cc-by-4.0"
    assert get_body["language"] == "en"


def test_patch_item_rejects_unknown_license(client):
    item_id = _seed_item(client)
    response = client.patch(f"/items/{item_id}", json={"license": "bogus"})
    assert response.status_code == 422


def test_patch_item_rejects_unknown_language(client):
    item_id = _seed_item(client)
    response = client.patch(f"/items/{item_id}", json={"language": "bogus"})
    assert response.status_code == 422
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_items_routes.py -k "license_and_language or unknown_license or unknown_language" -v`
Expected: FAIL (`KeyError: 'license'`)

- [ ] **Step 3: Modifier `core/app/items/schemas.py`**

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field, field_validator

from app.catalog.metadata import validate_language_id, validate_license_id
```

`ItemRead` gagne, après `keywords`, deux champs :

```python
    license: str = ""
    language: str = "fr"
```

`ItemUpdatePatch` devient :

```python
class ItemUpdatePatch(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    isPublished: bool | None = Field(default=None)
    slug: str | None = None
    license: str | None = None
    language: str | None = None

    @field_validator("license")
    @classmethod
    def _validate_license(cls, v: str | None) -> str | None:
        return validate_license_id(v)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str | None) -> str | None:
        return validate_language_id(v)
```

- [ ] **Step 4: Modifier `_to_read` dans `core/app/items/repository.py`**

```python
    return ItemRead(
        pk=item.id,
        resourceType=item.resource_type,
        slug=item.slug,
        title=item.title,
        abstract=item.abstract,
        owner=owner_username,
        thumbnailUrl=f"/items/{item.id}/thumbnail" if item.thumbnail_key else None,
        date=item.created_at.isoformat(),
        configId=None,
        isPublished=item.is_published,
        keywords=item.keywords or [],
        license=item.license,
        language=item.language,
        permissions=permissions,
    )
```

- [ ] **Step 5: Étendre `update_item` dans `core/app/items/repository.py`**

Signature :

```python
def update_item(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    title: str | None,
    abstract: str | None,
    keywords: list[str] | None,
    is_published: bool | None,
    slug: str | None = None,
    license: str | None = None,
    language: str | None = None,
    current_user_id: str | None = None,
) -> ItemRead | None:
```

Corps, juste après le bloc `if slug is not None: ...` :

```python
    if license is not None:
        item.license = license
    if language is not None:
        item.language = language
```

- [ ] **Step 6: Passer les deux champs depuis la route dans `core/app/items/routes.py`**

```python
        result = repo.update_item(
            session,
            tenant_id=user.tenant_id,
            item_id=item_id,
            title=patch.title,
            abstract=patch.abstract,
            keywords=patch.keywords,
            is_published=patch.isPublished,
            slug=patch.slug,
            license=patch.license,
            language=patch.language,
            current_user_id=user.id,
        )
```

- [ ] **Step 7: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_items_routes.py tests/test_items_repository.py tests/test_items_no_nplus1.py -v`
Expected: tous verts (le fichier `test_items_no_nplus1.py` sert de garde-fou : `update_item`/`_to_read` ne doivent introduire aucune requête supplémentaire par item).

- [ ] **Step 8: Portes de qualité**

Run: `cd core && uv run ruff check app/items && uv run ruff format --check app/items`
Expected: propre

- [ ] **Step 9: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/items/schemas.py core/app/items/repository.py core/app/items/routes.py core/tests/test_items_routes.py
git commit -m "feat(core): PATCH /items/{id} déclare licence et langue (SP-41)"
```

---

## Task 5: Export DCAT-AP

**Files:**
- Modify: `core/app/dcat/serializers.py`
- Modify: `core/app/dcat/routes.py`
- Modify: `core/tests/test_dcat_serializers.py`
- Modify: `core/tests/test_dcat_routes.py`

**Interfaces:**
- Consumes: `app.catalog.metadata.{resolve_license, resolve_frequency, resolve_language}` (Task 1), `Collection.{license,license_uri,producer,contact,update_frequency,lineage,language,version,temporal_start,temporal_end}` (Task 2).
- Produces: `serializers.dataset(...)` gagne 9 kwargs optionnels avec défauts identiques au comportement actuel (non-régression).

- [ ] **Step 1: Écrire les tests rouges dans `core/tests/test_dcat_serializers.py`**

D'abord, remplacer `test_context_has_expected_prefixes` (les deux nouveaux préfixes `vcard`/`rdfs` sont un changement volontaire et attendu, pas une régression) :

```python
def test_context_has_expected_prefixes():
    assert s.CONTEXT == {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "locn": "http://www.w3.org/ns/locn#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "vcard": "http://www.w3.org/2006/vcard/ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    }
```

Puis ajouter, en fin de fichier :

```python
def test_dataset_resolves_declared_license():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="etalab-2.0",
    )
    assert doc["dct:license"] == {"@id": "https://spdx.org/licenses/etalab-2.0.html"}


def test_dataset_other_license_uses_declared_uri():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="other",
        license_uri="https://example.org/my-license",
    )
    assert doc["dct:license"] == {"@id": "https://example.org/my-license"}


def test_dataset_other_license_without_uri_falls_back_to_license_other():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="other",
    )
    assert doc["dct:license"] == {"@id": s.LICENSE_OTHER}


def test_dataset_declared_language_overrides_default(dcat_shacl_shapes):
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        language="en",
    )
    assert doc["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/ENG"
    }
    standalone = {**doc, "@context": s.CONTEXT}
    g = rdflib.Graph()
    g.parse(data=json.dumps(standalone), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_omits_new_optional_fields_when_not_declared():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
    )
    assert "dct:accrualPeriodicity" not in doc
    assert "dct:provenance" not in doc
    assert "dcat:contactPoint" not in doc
    assert "dct:hasVersion" not in doc
    assert doc["dct:temporal"] == {
        "@type": "dct:PeriodOfTime",
        "dcat:startDate": {"@value": "2026-07-01T00:00:00Z", "@type": "xsd:dateTime"},
    }
    # dct:language N'EST PAS dans cette liste d'omission : contrairement aux
    # six champs ci-dessus, "language" n'a pas d'état non déclaré (défaut
    # "fr", jamais vide) — il apparaît donc inconditionnellement, exception
    # documentée à la spec §3/§7.2, pas une régression.
    assert doc["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/FRA"
    }


def test_dataset_declares_accrual_periodicity():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        update_frequency="monthly",
    )
    assert doc["dct:accrualPeriodicity"] == {
        "@id": "http://publications.europa.eu/resource/authority/frequency/MONTHLY"
    }


def test_dataset_declares_provenance():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        lineage="Relevé terrain 2026",
    )
    assert doc["dct:provenance"] == {
        "@type": "dct:ProvenanceStatement",
        "rdfs:label": "Relevé terrain 2026",
    }


def test_dataset_contact_point_email_heuristic():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        contact="contact@example.org",
    )
    assert doc["dcat:contactPoint"] == {
        "@type": "vcard:Kind",
        "vcard:hasEmail": "mailto:contact@example.org",
    }


def test_dataset_contact_point_plain_name():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        contact="Service SIG",
    )
    assert doc["dcat:contactPoint"] == {"@type": "vcard:Kind", "vcard:fn": "Service SIG"}


def test_dataset_declares_version():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        version="2.1",
    )
    assert doc["dct:hasVersion"] == "2.1"


def test_dataset_declared_temporal_extent():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        temporal_start="2020-01-01",
        temporal_end="2026-12-31",
    )
    assert doc["dct:temporal"] == {
        "@type": "dct:PeriodOfTime",
        "dcat:startDate": {"@value": "2020-01-01", "@type": "xsd:date"},
        "dcat:endDate": {"@value": "2026-12-31", "@type": "xsd:date"},
    }


def test_dataset_declared_temporal_extent_start_only():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        temporal_start="2020-01-01",
    )
    temporal = doc["dct:temporal"]
    assert temporal["dcat:startDate"] == {"@value": "2020-01-01", "@type": "xsd:date"}
    assert "dcat:endDate" not in temporal
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: FAIL (`TypeError: dataset() got an unexpected keyword argument 'license'`, et l'assertion `CONTEXT` échoue)

- [ ] **Step 3: Modifier `core/app/dcat/serializers.py`**

L'import en tête de fichier :

```python
import json
```

devient :

```python
import json

from app.catalog.metadata import resolve_frequency, resolve_language, resolve_license
```

`CONTEXT` devient :

```python
CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "locn": "http://www.w3.org/ns/locn#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}
```

Ajouter, juste avant `def dataset(`:

```python
def _contact_point(contact: str) -> dict:
    if "@" in contact:
        return {"@type": "vcard:Kind", "vcard:hasEmail": f"mailto:{contact}"}
    return {"@type": "vcard:Kind", "vcard:fn": contact}
```

`def dataset(...)` devient :

```python
def dataset(
    *,
    base: str,
    collection_id: str,
    title: str,
    description: str,
    created_at: str,
    updated_at: str,
    is_public: bool,
    publisher_name: str,
    bbox: list[float] | None,
    license: str = "",
    license_uri: str = "",
    language: str = "fr",
    update_frequency: str = "",
    lineage: str = "",
    contact: str = "",
    version: str = "",
    temporal_start: str | None = None,
    temporal_end: str | None = None,
) -> dict:
    license_entry = resolve_license(license) if license else None
    if license_entry is not None and license_entry.dcat_uri:
        license_id = {"@id": license_entry.dcat_uri}
    elif license == "other" and license_uri:
        license_id = {"@id": license_uri}
    else:
        license_id = {"@id": LICENSE_OTHER}

    temporal: dict = {"@type": "dct:PeriodOfTime"}
    if temporal_start or temporal_end:
        if temporal_start:
            temporal["dcat:startDate"] = {"@value": temporal_start, "@type": "xsd:date"}
        if temporal_end:
            temporal["dcat:endDate"] = {"@value": temporal_end, "@type": "xsd:date"}
    else:
        temporal["dcat:startDate"] = {"@value": created_at, "@type": "xsd:dateTime"}

    doc = {
        "@id": f"{base}/dcat/datasets/{collection_id}",
        "@type": "dcat:Dataset",
        "dct:identifier": collection_id,
        "dct:title": title,
        "dct:description": description or title or "No description provided.",
        "dct:issued": {"@value": created_at, "@type": "xsd:dateTime"},
        "dct:modified": {"@value": updated_at, "@type": "xsd:dateTime"},
        "dct:license": license_id,
        "dct:language": {
            "@id": (
                "http://publications.europa.eu/resource/authority/language/"
                f"{resolve_language(language).alpha3}"
            )
        },
        "dct:accessRights": {
            "@id": ACCESS_RIGHTS_PUBLIC if is_public else ACCESS_RIGHTS_RESTRICTED
        },
        "dct:publisher": publisher(base=base, name=publisher_name),
        "dct:spatial": {
            "@type": "dct:Location",
            "locn:geometry": {
                "@value": json.dumps(_bbox_polygon(bbox)),
                "@type": "https://www.iana.org/assignments/media-types/application/vnd.geo+json",
            },
        },
        "dct:temporal": temporal,
        "dcat:distribution": [
            distribution(
                title="GeoJSON (OGC API Features)",
                access_url=f"{base}/collections/{collection_id}/items",
                media_type="https://www.iana.org/assignments/media-types/application/geo+json",
                format_uri="http://publications.europa.eu/resource/authority/file-type/GEOJSON",
            ),
            distribution(
                title="STAC item-search",
                access_url=f"{base}/stac/collections/{collection_id}/items",
                format_uri="http://publications.europa.eu/resource/authority/file-type/JSON",
            ),
        ],
    }
    if update_frequency:
        freq_entry = resolve_frequency(update_frequency)
        if freq_entry is not None:
            doc["dct:accrualPeriodicity"] = {"@id": freq_entry.mdr_freq_uri}
    if lineage:
        doc["dct:provenance"] = {"@type": "dct:ProvenanceStatement", "rdfs:label": lineage}
    if contact:
        doc["dcat:contactPoint"] = _contact_point(contact)
    if version:
        doc["dct:hasVersion"] = version
    return doc
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: tous verts. **Vérification piège n°3** : si `test_dataset_declared_language_overrides_default` échoue sur la conformité SHACL (message `conforms=False` avec un texte mentionnant `dct:language`), c'est que la forme `{"@id": ...}` n'est pas celle attendue par `dcat-ap-SHACL.ttl` pour cette propriété sur un `dcat:Dataset` — dans ce cas, remplacer par la chaîne alpha-3 nue (`"dct:language": resolve_language(language).alpha3`, sans `{"@id": ...}`, cohérent avec la forme déjà utilisée par `catalog()` pour ce même prédicat) et relancer avant de continuer. Ne pas deviner : le texte d'échec de pyshacl dit exactement quelle forme est attendue.

- [ ] **Step 5: Écrire les tests rouges dans `core/tests/test_dcat_routes.py`**

Repérer la fonction `_register` (déjà lue en exploration) et ajouter, en fin de fichier :

```python
def test_dcat_dataset_reflects_declared_license(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/collections/incidents", json={"license": "etalab-2.0"})
    res = client.get("/dcat/datasets/incidents")
    assert res.json()["dct:license"] == {"@id": "https://spdx.org/licenses/etalab-2.0.html"}


def test_dcat_dataset_publisher_uses_producer_when_declared(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/collections/incidents", json={"producer": "Ma Régie"})
    res = client.get("/dcat/datasets/incidents")
    assert res.json()["dct:publisher"]["foaf:name"] == "Ma Régie"


def test_dcat_dataset_without_declared_metadata_omits_optional_fields(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    res = client.get("/dcat/datasets/incidents")
    body = res.json()
    assert body["dct:license"] == {"@id": "http://publications.europa.eu/resource/authority/licence/OTHER"}
    assert "dct:accrualPeriodicity" not in body
    assert "dct:provenance" not in body
    assert "dcat:contactPoint" not in body
    assert "dct:hasVersion" not in body
    # Exception assumée (spec §3/§7.2) : dct:language, lui, apparaît
    # désormais inconditionnellement (défaut "fr" jamais vide) — ce n'est
    # PAS un défaut de non-régression.
    assert body["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/FRA"
    }
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_dcat_routes.py -k "declared_license or producer_when_declared" -v`
Expected: FAIL (`AssertionError` — la route ne lit pas encore ces champs)

- [ ] **Step 7: Modifier `_dataset_doc` dans `core/app/dcat/routes.py`**

```python
def _dataset_doc(*, base, col, introspect, bbox_provider, rls, session, publisher_name):
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)
    return serializers.dataset(
        base=base,
        collection_id=col.id,
        title=col.title,
        description=col.description,
        created_at=_rfc3339(col.created_at),
        updated_at=_rfc3339(col.updated_at),
        is_public=col.is_public,
        publisher_name=col.producer or publisher_name,
        bbox=bbox,
        license=col.license,
        license_uri=col.license_uri,
        language=col.language,
        update_frequency=col.update_frequency,
        lineage=col.lineage,
        contact=col.contact,
        version=col.version,
        temporal_start=col.temporal_start.isoformat() if col.temporal_start else None,
        temporal_end=col.temporal_end.isoformat() if col.temporal_end else None,
    )
```

- [ ] **Step 8: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_dcat_routes.py tests/test_dcat_serializers.py tests/test_dcat_integration.py -v`
Expected: tous verts

- [ ] **Step 9: Portes de qualité**

Run: `cd core && uv run ruff check app/dcat && uv run ruff format --check app/dcat`
Expected: propre

- [ ] **Step 10: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/dcat/serializers.py core/app/dcat/routes.py core/tests/test_dcat_serializers.py core/tests/test_dcat_routes.py
git commit -m "feat(core): l'export DCAT-AP porte licence/producteur/contact/fréquence/généalogie/langue/version/emprise temporelle (SP-41)"
```

---

## Task 6: Export STAC

**Files:**
- Modify: `core/app/stac/serializers.py`
- Modify: `core/app/stac/routes.py`
- Modify: `core/tests/test_stac_serializers.py`
- Modify: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes: `app.catalog.metadata.resolve_license` (Task 1), `Collection.{license,producer,temporal_start,temporal_end}` (Task 2).
- Produces: `serializers.collection(...)` gagne 3 kwargs optionnels avec défauts identiques au comportement actuel (non-régression).

- [ ] **Step 1: Écrire les tests rouges dans `core/tests/test_stac_serializers.py`**

```python
def test_collection_resolves_declared_license_to_spdx_id():
    doc = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        bbox=None,
        temporal_start="2026-07-01T00:00:00Z",
        license="etalab-2.0",
    )
    assert doc["license"] == "etalab-2.0"


def test_collection_unknown_license_falls_back_to_other():
    doc = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        bbox=None,
        temporal_start="2026-07-01T00:00:00Z",
        license="",
    )
    assert doc["license"] == "other"


def test_collection_providers_present_only_when_declared():
    without = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        bbox=None,
        temporal_start="2026-07-01T00:00:00Z",
    )
    assert "providers" not in without

    with_providers = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        bbox=None,
        temporal_start="2026-07-01T00:00:00Z",
        providers=[{"name": "Ma Régie", "roles": ["producer"]}],
    )
    assert with_providers["providers"] == [{"name": "Ma Régie", "roles": ["producer"]}]


def test_collection_declared_temporal_extent():
    doc = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        bbox=None,
        temporal_start="2020-01-01",
        temporal_end="2026-12-31",
    )
    assert doc["extent"]["temporal"]["interval"] == [["2020-01-01", "2026-12-31"]]
```

(`BASE = "http://testserver"` est déjà défini en tête de `test_stac_serializers.py` — vérifié, aucune redéfinition nécessaire.)

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -v`
Expected: FAIL (`TypeError: collection() got an unexpected keyword argument 'license'`)

- [ ] **Step 3: Modifier `core/app/stac/serializers.py`**

Ajouter en tête de fichier (après le docstring du module) :

```python
from app.catalog.metadata import resolve_license
```

`def collection(...)` devient :

```python
def collection(
    *,
    base: str,
    collection_id: str,
    title: str,
    description: str,
    bbox: list[float] | None,
    temporal_start: str | None,
    license: str = "",
    providers: list[dict] | None = None,
    temporal_end: str | None = None,
) -> dict:
    entry = resolve_license(license) if license else None
    doc = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "id": collection_id,
        "title": title,
        "description": description or title or "No description provided.",
        "license": entry.spdx_id if entry else "other",
        "extent": {
            "spatial": {"bbox": [bbox if bbox is not None else list(WORLD_BBOX)]},
            "temporal": {"interval": [[temporal_start, temporal_end]]},
        },
        "links": [
            {
                "rel": "self",
                "type": "application/json",
                "href": f"{base}/stac/collections/{collection_id}",
            },
            {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
            {"rel": "parent", "type": "application/json", "href": f"{base}/stac"},
            {
                "rel": "items",
                "type": "application/geo+json",
                "href": f"{base}/stac/collections/{collection_id}/items",
            },
        ],
    }
    if providers:
        doc["providers"] = providers
    if bbox is None:
        doc["note"] = "Emprise indisponible (pas de géométrie ou table vide) : repli emprise monde."
    return doc
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -v`
Expected: tous verts

- [ ] **Step 5: Écrire les tests rouges dans `core/tests/test_stac_routes.py`**

Ce fichier a le même patron `env`/`_register`/`_as` que `test_dcat_routes.py` (`env` renvoie `(app, client, admin, regular, Session)`, `_register(app, client, admin, public=False)`) — vérifié directement dans le fichier. Ajouter en fin de fichier :

```python
def test_stac_collection_reflects_declared_license(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/collections/incidents", json={"license": "cc-by-4.0"})
    res = client.get("/stac/collections/incidents")
    assert res.json()["license"] == "CC-BY-4.0"


def test_stac_collection_providers_only_when_producer_declared(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    res_without = client.get("/stac/collections/incidents")
    assert "providers" not in res_without.json()

    _as(app, admin)
    client.patch("/collections/incidents", json={"producer": "Ma Régie"})
    res_with = client.get("/stac/collections/incidents")
    assert res_with.json()["providers"] == [{"name": "Ma Régie", "roles": ["producer"]}]
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_stac_routes.py -k "declared_license or producer_declared" -v`
Expected: FAIL

- [ ] **Step 7: Modifier `core/app/stac/routes.py`**

Les deux call sites de `serializers.collection(...)` (`list_collections` et `get_collection`) partagent le même patron. Dans chacun, remplacer :

```python
        docs.append(
            serializers.collection(
                base=_base(request),
                collection_id=col.id,
                title=col.title,
                description=col.description or "",
                bbox=bbox,
                temporal_start=_rfc3339(col.created_at),
            )
        )
```

par :

```python
        docs.append(
            serializers.collection(
                base=_base(request),
                collection_id=col.id,
                title=col.title,
                description=col.description or "",
                bbox=bbox,
                temporal_start=(
                    col.temporal_start.isoformat()
                    if col.temporal_start
                    else _rfc3339(col.created_at)
                ),
                temporal_end=col.temporal_end.isoformat() if col.temporal_end else None,
                license=col.license,
                providers=(
                    [{"name": col.producer, "roles": ["producer"]}] if col.producer else None
                ),
            )
        )
```

et, dans `get_collection` :

```python
    return serializers.collection(
        base=_base(request),
        collection_id=col.id,
        title=col.title,
        description=col.description or "",
        bbox=bbox,
        temporal_start=(
            col.temporal_start.isoformat() if col.temporal_start else _rfc3339(col.created_at)
        ),
        temporal_end=col.temporal_end.isoformat() if col.temporal_end else None,
        license=col.license,
        providers=[{"name": col.producer, "roles": ["producer"]}] if col.producer else None,
    )
```

- [ ] **Step 8: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_stac_routes.py tests/test_stac_serializers.py tests/test_stac_integration.py tests/test_stac_search.py -v`
Expected: tous verts

- [ ] **Step 9: Portes de qualité**

Run: `cd core && uv run ruff check app/stac && uv run ruff format --check app/stac`
Expected: propre

- [ ] **Step 10: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/stac/serializers.py core/app/stac/routes.py core/tests/test_stac_serializers.py core/tests/test_stac_routes.py
git commit -m "feat(core): l'export STAC porte licence/producteur/emprise temporelle déclarés (SP-41)"
```

---

## Task 7: Régénération OpenAPI/TS + types et client shell

**Files:**
- Modify: `core/openapi.json` (généré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (généré)
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/test/msw/handlers.ts`

**Interfaces:**
- Consumes: routes/schémas des Tasks 1, 3, 4, 5, 6 (déjà en place côté cœur).
- Produces (consommé par Task 8, 9) : `MetadataCatalog` (type shell), `client.getMetadataCatalog(): Promise<MetadataCatalog>`, `useMetadataCatalog()` (hook TanStack Query).

- [ ] **Step 1: Régénérer la spec OpenAPI + les types TS (piège n°1)**

Run:
```bash
cd /home/lenen/projets/geostudio/core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` modifiés (diff **non vide** — nouvelle route `/metadata-catalog`, nouveaux champs sur `CollectionRead`-équivalent et `ItemRead`).

- [ ] **Step 2: Ajouter le type `MetadataCatalog` dans `shell/src/api/types.ts`**

Juste après `export type ItemPage = {...}`, ajouter :

```typescript
export type LicenseCatalogEntry = { id: string; label: string; dcatUri: string | null; spdxId: string };
export type FrequencyCatalogEntry = { id: string; label: string };
export type LanguageCatalogEntry = { id: string; label: string };
export type MetadataCatalog = {
  licenses: LicenseCatalogEntry[];
  frequencies: FrequencyCatalogEntry[];
  languages: LanguageCatalogEntry[];
};
```

`Item` gagne, après `keywords?: string[];` :

```typescript
  license: string;
  language: string;
```

`UpdatePatch` gagne, après `slug?: string;` :

```typescript
  license?: string;
  language?: string;
```

`CollectionAdmin` gagne, après `attachmentFields: { key: string; label: string }[];` :

```typescript
  license: string;
  licenseUri: string;
  producer: string;
  contact: string;
  updateFrequency: string;
  lineage: string;
  language: string;
  version: string;
  temporalStart: string | null;
  temporalEnd: string | null;
```

`CollectionPatchInput` gagne, après `attachmentFields?: { key: string; label: string }[];` :

```typescript
  license?: string;
  licenseUri?: string;
  producer?: string;
  contact?: string;
  updateFrequency?: string;
  lineage?: string;
  language?: string;
  version?: string;
  temporalStart?: string | null;
  temporalEnd?: string | null;
```

- [ ] **Step 3: Ajouter `getMetadataCatalog` à l'interface `ItemClient` et à son implémentation dans `shell/src/api/itemClient.ts`**

Dans l'interface (`ItemClient`), ajouter une entrée (proche de `listCollections`) :

```typescript
  getMetadataCatalog(): Promise<MetadataCatalog>;
```

Dans l'objet retourné par `createItemClient` (proche de `getItem`), ajouter :

```typescript
    async getMetadataCatalog(): Promise<MetadataCatalog> {
      return request<MetadataCatalog>("GET", "/metadata-catalog");
    },
```

Ajouter `MetadataCatalog` à l'import de types en tête de fichier (le fichier importe déjà `Item`, `CollectionAdmin`, etc. depuis `"./types"` — ajouter `MetadataCatalog` à cette même liste).

- [ ] **Step 4: Ajouter `useMetadataCatalog` dans `shell/src/api/hooks.ts`**

Juste après `useCollectionsAdmin`, ajouter :

```typescript
export function useMetadataCatalog() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["metadata-catalog"],
    queryFn: () => client.getMetadataCatalog(),
    staleTime: Infinity, // catalogue statique côté cœur, jamais invalidé
  });
}
```

- [ ] **Step 5: Ajouter le handler MSW par défaut dans `shell/src/test/msw/handlers.ts`**

Juste après `http.get(\`${CORE}/instance\`, ...)`, ajouter :

```typescript
  http.get(`${CORE}/metadata-catalog`, () =>
    HttpResponse.json({
      licenses: [
        {
          id: "etalab-2.0",
          label: "Licence Ouverte / Open Licence 2.0 (Etalab)",
          dcatUri: "https://spdx.org/licenses/etalab-2.0.html",
          spdxId: "etalab-2.0",
        },
        { id: "cc0-1.0", label: "CC0 1.0 Universal", dcatUri: null, spdxId: "CC0-1.0" },
        { id: "proprietary", label: "Propriétaire (aucune réutilisation)", dcatUri: null, spdxId: "proprietary" },
        { id: "other", label: "Autre (URI à saisir)", dcatUri: null, spdxId: "other" },
      ],
      frequencies: [
        { id: "daily", label: "Quotidienne" },
        { id: "monthly", label: "Mensuelle" },
        { id: "annual", label: "Annuelle" },
      ],
      languages: [
        { id: "fr", label: "Français" },
        { id: "en", label: "Anglais" },
      ],
    }),
  ),
```

- [ ] **Step 6: Vérifier le typecheck shell**

Run: `cd /home/lenen/projets/geostudio/shell && npx tsc --noEmit`
Expected: erreurs sur `EditCollectionPanel.test.tsx` (fixture `baseCollection` incomplète — traité Task 8) et éventuellement `MetadataForm.test.tsx`/`ItemDetailPage.test.tsx` (traité Task 9). Aucune erreur ailleurs (`itemClient.ts`, `types.ts`, `hooks.ts` doivent typechecker proprement dès ce Step).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/openapi.json shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/test/msw/handlers.ts
git commit -m "feat(shell): types et client pour le catalogue de métadonnées + nouveaux champs Item/Collection (SP-41)"
```

---

## Task 8: `EditCollectionPanel.tsx` — onglets et nouveaux champs

**Files:**
- Modify: `shell/src/shell/EditCollectionPanel.tsx`
- Modify: `shell/src/shell/EditCollectionPanel.test.tsx`

**Interfaces:**
- Consumes: `useMetadataCatalog` (Task 7), `CollectionAdmin`/`CollectionPatchInput` étendus (Task 7), `ui/kit/Tabs`, `ui/kit/Select`, `ui/kit/Textarea` (déjà livrés SP-29b).

- [ ] **Step 1: Mettre à jour `baseCollection` et le mock de hooks dans `shell/src/shell/EditCollectionPanel.test.tsx`**

L'objet `baseCollection` devient :

```typescript
const baseCollection: CollectionAdmin = {
  id: "incidents",
  title: "Incidents",
  description: "",
  tableName: "incidents",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 3,
  owner: "admin",
  attachmentFields: [],
  license: "",
  licenseUri: "",
  producer: "",
  contact: "",
  updateFrequency: "",
  lineage: "",
  language: "fr",
  version: "",
  temporalStart: null,
  temporalEnd: null,
};
```

Les imports/mocks en tête de fichier deviennent :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CollectionAdmin } from "../api/types";
import { EditCollectionPanel } from "./EditCollectionPanel";

// jsdom n'implémente pas ces API navigateur consommées par Radix Select
// (piège n°10) — stub local à ce fichier.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const { mockUseUpdateCollection, mockUseInstanceInfo, mockUseMetadataCatalog } = vi.hoisted(
  () => ({
    mockUseUpdateCollection: vi.fn(),
    mockUseInstanceInfo: vi.fn(),
    mockUseMetadataCatalog: vi.fn(),
  }),
);

vi.mock("../api/hooks", () => ({
  useUpdateCollection: mockUseUpdateCollection,
  useInstanceInfo: mockUseInstanceInfo,
  useMetadataCatalog: mockUseMetadataCatalog,
}));
```

Et le `beforeEach` devient :

```typescript
beforeEach(() => {
  mockUseUpdateCollection.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    isError: false,
  });
  mockUseInstanceInfo.mockReturnValue({ data: { readOnly: false } });
  mockUseMetadataCatalog.mockReturnValue({
    data: {
      licenses: [
        { id: "etalab-2.0", label: "Licence Ouverte / Open Licence 2.0 (Etalab)", dcatUri: null, spdxId: "etalab-2.0" },
        { id: "other", label: "Autre (URI à saisir)", dcatUri: null, spdxId: "other" },
      ],
      frequencies: [{ id: "monthly", label: "Mensuelle" }],
      languages: [
        { id: "fr", label: "Français" },
        { id: "en", label: "Anglais" },
      ],
    },
  });
});
```

Les deux tests existants (`"affiche les champs attachment déjà déclarés"` et `"ajoute puis soumet un nouveau champ attachment"`) doivent maintenant naviguer vers l'onglet « Pièces jointes » avant d'interagir avec ces champs — ajouter, en tête de chacun des deux `it(...)`, juste après le `render(...)` :

```typescript
    await userEvent.click(screen.getByRole("tab", { name: "Pièces jointes" }));
```

- [ ] **Step 2: Ajouter les tests rouges pour les métadonnées ouvertes, en fin de fichier**

```typescript
describe("EditCollectionPanel — métadonnées ouvertes (SP-41)", () => {
  it("affiche les valeurs déjà déclarées", async () => {
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, producer: "Ma Régie", version: "1.0" }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    expect(screen.getByLabelText("Producteur")).toHaveValue("Ma Régie");
    expect(screen.getByLabelText("Version")).toHaveValue("1.0");
  });

  it("soumet une licence choisie", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
    await userEvent.click(
      await screen.findByRole("option", { name: "Licence Ouverte / Open Licence 2.0 (Etalab)" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ license: "etalab-2.0" }),
    );
  });

  it("révèle le champ URI seulement pour la licence Autre", async () => {
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    expect(screen.queryByLabelText("URI de la licence")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
    await userEvent.click(await screen.findByRole("option", { name: "Autre (URI à saisir)" }));
    expect(screen.getByLabelText("URI de la licence")).toBeInTheDocument();
  });

  it("envoie une chaîne vide quand la licence redevient non déclarée", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, license: "etalab-2.0" }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ license: "etalab-2.0" }),
    );
  });

  it("envoie null pour une emprise temporelle non renseignée", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ temporalStart: null, temporalEnd: null }),
    );
  });
});
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils échouent**

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx`
Expected: FAIL (`Unable to find role="tab"` — le composant n'a pas encore d'onglets)

- [ ] **Step 4: Réécrire `shell/src/shell/EditCollectionPanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useMetadataCatalog, useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Select } from "../ui/kit/Select";
import { Tabs } from "../ui/kit/Tabs";
import { Textarea } from "../ui/kit/Textarea";

const UNSET = "unset";

export function EditCollectionPanel({
  collection,
  onClose,
}: {
  collection: CollectionAdmin;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const catalogQuery = useMetadataCatalog();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);
  const [attachmentFields, setAttachmentFields] = useState(collection.attachmentFields ?? []);
  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [license, setLicense] = useState(collection.license || UNSET);
  const [licenseUri, setLicenseUri] = useState(collection.licenseUri);
  const [producer, setProducer] = useState(collection.producer);
  const [contact, setContact] = useState(collection.contact);
  const [updateFrequency, setUpdateFrequency] = useState(collection.updateFrequency || UNSET);
  const [lineage, setLineage] = useState(collection.lineage);
  const [language, setLanguage] = useState(collection.language);
  const [version, setVersion] = useState(collection.version);
  const [temporalStart, setTemporalStart] = useState(collection.temporalStart ?? "");
  const [temporalEnd, setTemporalEnd] = useState(collection.temporalEnd ?? "");

  const licenseOptions = [
    { value: UNSET, label: "Aucune licence déclarée" },
    ...(catalogQuery.data?.licenses.map((l) => ({ value: l.id, label: l.label })) ?? []),
  ];
  const frequencyOptions = [
    { value: UNSET, label: "Non renseignée" },
    ...(catalogQuery.data?.frequencies.map((f) => ({ value: f.id, label: f.label })) ?? []),
  ];
  const languageOptions =
    catalogQuery.data?.languages.map((l) => ({ value: l.id, label: l.label })) ?? [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({
        title,
        description,
        isPublic,
        editable,
        attachmentFields,
        license: license === UNSET ? "" : license,
        licenseUri,
        producer,
        contact,
        updateFrequency: updateFrequency === UNSET ? "" : updateFrequency,
        lineage,
        language,
        version,
        temporalStart: temporalStart || null,
        temporalEnd: temporalEnd || null,
      });
      onClose();
    } catch {
      // surfaced via updateCollection.isError
    }
  }

  function addAttachmentField() {
    const key = draftKey.trim();
    const label = draftLabel.trim();
    if (!key || !label || attachmentFields.some((f) => f.key === key)) return;
    setAttachmentFields((fields) => [...fields, { key, label }]);
    setDraftKey("");
    setDraftLabel("");
  }

  function removeAttachmentField(key: string) {
    setAttachmentFields((fields) => fields.filter((f) => f.key !== key));
  }

  return (
    <section aria-label={`Éditer ${collection.title}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {collection.title}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <Tabs
          aria-label="Sections d'édition"
          defaultValue="general"
          tabs={[
            {
              value: "general",
              label: "Général",
              content: (
                <div className="flex flex-col gap-3 pt-3">
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Titre
                    <Input
                      aria-label="Titre"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Description
                    <Input
                      aria-label="Description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm text-ink">
                    <input
                      type="checkbox"
                      aria-label="Public"
                      checked={isPublic}
                      onChange={(e) => setIsPublic(e.target.checked)}
                    />
                    Public
                  </label>
                  <label className="flex items-center gap-2 text-sm text-ink">
                    <input
                      type="checkbox"
                      aria-label="Éditable"
                      checked={editable}
                      onChange={(e) => setEditable(e.target.checked)}
                    />
                    Éditable
                  </label>
                </div>
              ),
            },
            {
              value: "metadata",
              label: "Métadonnées ouvertes",
              content: (
                <div className="flex flex-col gap-3 pt-3">
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Licence
                    <Select
                      aria-label="Licence"
                      value={license}
                      onValueChange={setLicense}
                      options={licenseOptions}
                    />
                  </label>
                  {license === "other" && (
                    <label className="flex flex-col gap-1 text-sm text-ink">
                      URI de la licence
                      <Input
                        aria-label="URI de la licence"
                        value={licenseUri}
                        onChange={(e) => setLicenseUri(e.target.value)}
                      />
                    </label>
                  )}
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Producteur
                    <Input
                      aria-label="Producteur"
                      value={producer}
                      onChange={(e) => setProducer(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Contact
                    <Input
                      aria-label="Contact"
                      value={contact}
                      onChange={(e) => setContact(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Fréquence de mise à jour
                    <Select
                      aria-label="Fréquence de mise à jour"
                      value={updateFrequency}
                      onValueChange={setUpdateFrequency}
                      options={frequencyOptions}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Généalogie
                    <Textarea
                      aria-label="Généalogie"
                      value={lineage}
                      onChange={(e) => setLineage(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Langue
                    <Select
                      aria-label="Langue"
                      value={language}
                      onValueChange={setLanguage}
                      options={languageOptions}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Version
                    <Input
                      aria-label="Version"
                      value={version}
                      onChange={(e) => setVersion(e.target.value)}
                    />
                  </label>
                  <div className="flex gap-2">
                    <label className="flex flex-1 flex-col gap-1 text-sm text-ink">
                      Début
                      <Input
                        type="date"
                        aria-label="Début de l'emprise temporelle"
                        value={temporalStart}
                        onChange={(e) => setTemporalStart(e.target.value)}
                      />
                    </label>
                    <label className="flex flex-1 flex-col gap-1 text-sm text-ink">
                      Fin
                      <Input
                        type="date"
                        aria-label="Fin de l'emprise temporelle"
                        value={temporalEnd}
                        onChange={(e) => setTemporalEnd(e.target.value)}
                      />
                    </label>
                  </div>
                </div>
              ),
            },
            {
              value: "attachments",
              label: "Pièces jointes",
              content: (
                <div className="flex flex-col gap-1 pt-3">
                  <p className="text-sm font-medium text-ink">Champs de pièces jointes</p>
                  <ul className="flex flex-col gap-1">
                    {attachmentFields.map((f) => (
                      <li key={f.key} className="flex items-center gap-2">
                        <Input
                          aria-label={`Clé existante : ${f.key}`}
                          value={f.key}
                          readOnly
                          className="text-xs"
                        />
                        <Input
                          aria-label={`Libellé existant : ${f.key}`}
                          value={f.label}
                          readOnly
                          className="text-xs"
                        />
                        <button
                          type="button"
                          className="text-danger underline text-xs"
                          onClick={() => removeAttachmentField(f.key)}
                        >
                          Retirer
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2">
                    <Input
                      aria-label="Clé du champ"
                      value={draftKey}
                      onChange={(e) => setDraftKey(e.target.value)}
                    />
                    <Input
                      aria-label="Libellé du champ"
                      value={draftLabel}
                      onChange={(e) => setDraftLabel(e.target.value)}
                    />
                    <Button type="button" variant="outline" size="sm" onClick={addAttachmentField}>
                      Ajouter un champ
                    </Button>
                  </div>
                </div>
              ),
            },
          ]}
        />
        {updateCollection.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateCollection.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx`
Expected: tous verts

- [ ] **Step 6: Typecheck + lint**

Run: `cd shell && npx tsc --noEmit && npm run lint`
Expected: propre pour ce fichier (des erreurs peuvent subsister sur `MetadataForm.test.tsx`/`ItemDetailPage.test.tsx`, traitées Task 9)

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/EditCollectionPanel.tsx shell/src/shell/EditCollectionPanel.test.tsx
git commit -m "feat(shell): EditCollectionPanel gagne un onglet Métadonnées ouvertes (SP-41)"
```

---

## Task 9: `MetadataForm.tsx` (licence + langue) + correctif du bug keywords

**Files:**
- Modify: `shell/src/ui/MetadataForm.tsx`
- Modify: `shell/src/ui/MetadataForm.test.tsx`
- Modify: `shell/src/pages/ItemDetailPage.tsx`
- Modify: `shell/src/pages/ItemDetailPage.test.tsx`

**Interfaces:**
- Consumes: `useMetadataCatalog` (Task 7).

- [ ] **Step 1: Mettre à jour les tests existants de `shell/src/ui/MetadataForm.test.tsx` et en ajouter deux**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MetadataForm } from "./MetadataForm";

// jsdom n'implémente pas ces API navigateur consommées par Radix Select
// (piège n°10) — stub local à ce fichier.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const LICENSES = [{ id: "etalab-2.0", label: "Licence Ouverte / Open Licence 2.0 (Etalab)" }];
const LANGUAGES = [
  { id: "fr", label: "Français" },
  { id: "en", label: "Anglais" },
];

test("submits trimmed title, abstract and split keywords", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "Old", abstract: "A", keywords: ["k1"], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  const title = screen.getByLabelText("Titre");
  await userEvent.clear(title);
  await userEvent.type(title, "  New  ");
  const kw = screen.getByLabelText("Mots-clés");
  await userEvent.clear(kw);
  await userEvent.type(kw, "a, b ,c");
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).toHaveBeenCalledWith({
    title: "New",
    abstract: "A",
    keywords: ["a", "b", "c"],
    license: "",
    language: "fr",
  });
});

test("does not submit an empty title", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "", abstract: "", keywords: [], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});

test("pré-remplit les mots-clés existants (non-régression du bug d'ItemDetailPage)", () => {
  render(
    <MetadataForm
      initial={{
        title: "T",
        abstract: "A",
        keywords: ["existing-tag"],
        license: "",
        language: "fr",
      }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={vi.fn()}
      onCancel={() => {}}
    />,
  );
  expect(screen.getByLabelText("Mots-clés")).toHaveValue("existing-tag");
});

test("soumet la licence et la langue choisies", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "T", abstract: "", keywords: [], license: "", language: "fr" }}
      licenses={LICENSES}
      languages={LANGUAGES}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Licence" }));
  await userEvent.click(
    await screen.findByRole("option", { name: "Licence Ouverte / Open Licence 2.0 (Etalab)" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Langue" }));
  await userEvent.click(await screen.findByRole("option", { name: "Anglais" }));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ license: "etalab-2.0", language: "en" }),
  );
});
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd shell && npx vitest run src/ui/MetadataForm.test.tsx`
Expected: FAIL (props `licenses`/`languages` non reconnues par le composant, `initial.license`/`initial.language` requis par le type mais absents de l'ancien composant)

- [ ] **Step 3: Réécrire `shell/src/ui/MetadataForm.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Button } from "./kit/Button";
import { Input } from "./kit/Input";
import { Select } from "./kit/Select";

const UNSET = "unset";

export function MetadataForm({
  initial,
  licenses,
  languages,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
  };
  licenses: { id: string; label: string }[];
  languages: { id: string; label: string }[];
  onSubmit: (v: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
  }) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [title, setTitle] = useState(initial.title);
  const [abstract, setAbstract] = useState(initial.abstract);
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));
  const [license, setLicense] = useState(initial.license || UNSET);
  const [language, setLanguage] = useState(initial.language);

  const licenseOptions = [
    { value: UNSET, label: "Aucune licence déclarée" },
    ...licenses.map((l) => ({ value: l.id, label: l.label })),
  ];
  const languageOptions = languages.map((l) => ({ value: l.id, label: l.label }));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    onSubmit({
      title: clean,
      abstract,
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
      license: license === UNSET ? "" : license,
      language,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm text-ink">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Résumé
        <textarea
          aria-label="Résumé"
          className="min-h-20 rounded-md border border-rule bg-surface px-3 py-2 text-sm text-ink"
          value={abstract}
          onChange={(e) => setAbstract(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Mots-clés
        <Input
          aria-label="Mots-clés"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Licence
        <Select
          aria-label="Licence"
          value={license}
          onValueChange={setLicense}
          options={licenseOptions}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Langue
        <Select
          aria-label="Langue"
          value={language}
          onValueChange={setLanguage}
          options={languageOptions}
        />
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" size="sm" disabled={pending || !title.trim()}>
          Enregistrer
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd shell && npx vitest run src/ui/MetadataForm.test.tsx`
Expected: tous verts

- [ ] **Step 5: Mettre à jour `shell/src/pages/ItemDetailPage.tsx`**

L'import :

```typescript
import { useItem, useUpdateItem, useUploadThumbnail } from "../api/hooks";
```

devient :

```typescript
import { useItem, useMetadataCatalog, useUpdateItem, useUploadThumbnail } from "../api/hooks";
```

Dans le corps du composant, après `const thumbnail = useUploadThumbnail(pk);`, ajouter :

```typescript
  const catalogQuery = useMetadataCatalog();
```

`save()` devient :

```typescript
  async function save(v: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
  }) {
    try {
      await update.mutateAsync(v);
      closePanel();
    } catch {
      /* surfaced via update.isError */
    }
  }
```

Les deux occurrences de `<MetadataForm initial={{ title: item.title, abstract: item.abstract, keywords: [] }} .../>` (lignes ~132-137 et ~152-157) deviennent chacune :

```tsx
                      <MetadataForm
                        initial={{
                          title: item.title,
                          abstract: item.abstract,
                          keywords: item.keywords ?? [],
                          license: item.license,
                          language: item.language,
                        }}
                        licenses={catalogQuery.data?.licenses ?? []}
                        languages={catalogQuery.data?.languages ?? []}
                        onSubmit={(v) => void save(v)}
                        onCancel={closePanel}
                        pending={update.isPending}
                      />
```

(pour la seconde occurrence, dans la branche `Locked`, `onSubmit={(v) => void save(v)}` reste `onSubmit={closePanel}` comme aujourd'hui — seul le contenu de `initial` et les deux nouvelles props `licenses`/`languages` changent ; ne pas toucher `onSubmit`/`pending` de cette branche.)

- [ ] **Step 6: Ajouter le test rouge de non-régression dans `shell/src/pages/ItemDetailPage.test.tsx`**

Après le test `"affiche le formulaire d'édition quand l'URL porte ?panel=edit"`, ajouter :

```typescript
test("conserve les mots-clés existants à l'ouverture du panneau Éditer", async () => {
  server.use(
    http.get("https://core.test/items/1", () =>
      HttpResponse.json({
        pk: "1",
        resourceType: "app",
        title: "Item 1",
        abstract: "Abstract 1",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01T00:00:00Z",
        configId: null,
        isPublished: false,
        keywords: ["existing-tag"],
        license: "",
        language: "fr",
        permissions: { read: true, write: true, delete: true, share: true },
      }),
    ),
  );
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=edit", children),
  });
  expect(await screen.findByLabelText("Mots-clés")).toHaveValue("existing-tag");
});
```

- [ ] **Step 7: Lancer le test, vérifier qu'il échoue avant le correctif**

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx -t "conserve les mots-clés"`
Expected: FAIL si le Step 5 n'a pas encore été appliqué (`toHaveValue("existing-tag")` reçoit `""`) — si le Step 5 est déjà fait au moment d'exécuter cette commande, revenir temporairement sur `keywords: item.keywords ?? []` → `keywords: []` dans `ItemDetailPage.tsx`, confirmer l'échec, puis restaurer (falsification du filet, piège n°10).

- [ ] **Step 8: Lancer toute la suite `ItemDetailPage.test.tsx`, vérifier qu'elle passe**

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx`
Expected: tous verts

- [ ] **Step 9: Typecheck + lint shell complets**

Run: `cd shell && npx tsc --noEmit && npm run lint && npm run format:check`
Expected: propre

- [ ] **Step 10: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/ui/MetadataForm.tsx shell/src/ui/MetadataForm.test.tsx shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx
git commit -m "fix(shell): MetadataForm porte licence+langue et ne perd plus les mots-clés existants (SP-41)"
```

---

## Task 10: Vérification finale

**Files:** aucun fichier de production — vérification uniquement, correctifs ponctuels si nécessaire.

**Interfaces:** aucune (dernière tâche, consomme tout ce qui précède).

- [ ] **Step 1: Suite complète cœur**

Run: `cd core && uv run pytest`
Expected: tous verts hors les deux échecs préexistants documentés dans CLAUDE.md (`test_features_rls.py::test_scope_preserves_original_sql_error` intermittent, `test_deployability.py::test_every_compose_substitution_is_documented`) — si un troisième échec apparaît, l'attribuer explicitement à ce plan et le corriger avant de continuer.

- [ ] **Step 2: Portes de qualité cœur**

Run:
```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```
Expected: tout propre, couverture ≥ 85 %.

- [ ] **Step 3: Suite complète shell + couverture**

Run:
```bash
cd shell
rm -rf dist dist-export
npx vitest run --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
npm run lint && npm run format:check
```
Expected: tout vert, couverture ≥ 88 %, `tsc --noEmit`/`vite build` propres.

- [ ] **Step 4: Suite E2E complète (piège n°6)**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: pas de nouvelle régression par rapport à la référence CLAUDE.md avant ce plan (dernier chiffre connu : 144 tests/140 passed/4 skipped/0 failed, SP-38). Vérifier via `cat shell/test-results/.last-run.json` (pas seulement la fin de la sortie du reporter `list`, piège méthodologique documenté SP-31) : `status` doit être `"passed"` et `failedTests` vide.

- [ ] **Step 5: `uvx pre-commit run --all-files`**

Run: `uvx pre-commit run --all-files`
Expected: les 5 hooks passent (commitlint ne s'exécute qu'au commit, pas ici).

- [ ] **Step 6: Revue finale de branche**

Dispatcher une revue finale de branche (modèle le plus capable disponible) sur l'ensemble des commits de ce plan (`git log main..HEAD` scopé à ce travail), avec le brief suivant : vérifier en particulier (a) que le critère de non-régression §7.2 de la spec tient réellement — comparer un export DCAT-AP et un export STAC d'une collection qui ne déclare rien de nouveau avant/après ce plan, byte pour byte sur les clés existantes ; (b) que le mapping `""`/`None` (chaîne vide = non déclaré, `None` PATCH = champ omis) est appliqué de façon cohérente sur les deux domaines (Collection, Item) sans confusion résiduelle ; (c) qu'aucun chemin de lecture n'a été oublié (piège n°5) sur les nouveaux champs, en particulier `temporalStart`/`temporalEnd` qui transitent par des types `date` côté cœur et `string | null` côté shell. Appliquer et re-vérifier tout correctif trouvé, comme pour toute revue finale de ce dépôt.

- [ ] **Step 7: Mettre à jour `CLAUDE.md`**

Ajouter une entrée `### Livré` pour SP-41 (chantier 4.9, B1+B2), suivant le format des entrées précédentes (SP-38 à SP-40) : ce qui a été livré, les compteurs de suites (cœur/shell/E2E) mesurés à cette clôture, les défauts trouvés en revue finale et leur statut, tout suivi non bloquant documenté. Retirer B2/B1 de la liste des constats ouverts s'ils y figurent encore ailleurs dans le document (vérifier — au moment d'écrire ce plan, B1/B2 n'apparaissent que dans le corps du texte narratif du plan d'action, pas dans une liste `### À venir` de CLAUDE.md, donc probablement rien à retirer ; confirmer avant de conclure qu'il n'y a rien à faire ici).

- [ ] **Step 8: Commit de clôture**

```bash
cd /home/lenen/projets/geostudio
git add CLAUDE.md
git commit -m "docs: clôture SP-41 — métadonnées éditables et licence par jeu (chantier 4.9)"
```
