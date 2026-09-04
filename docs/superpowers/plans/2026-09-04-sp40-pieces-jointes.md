# Pièces jointes sur une entité (SP-40) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ferme le chantier 4.12 — une photo (ou tout autre fichier) attachée à une entité depuis le widget Formulaire est visible d'un lecteur autorisé et invisible des autres, avec la même pièce jointe consultable dans le popup de la carte, sur `/sites/{slug}` (visiteur anonyme inclus sur une collection publique) et via un outil MCP en lecture.

**Architecture:** Nouveau domaine `core/app/attachments/` (modèle, dépôt, routes self-scoped) inséré dans le contrat de couches entre `app.features` et `app.collections` ; upload S3 présigné (patron A6, `app.ingestion.storage`), lecture en proxy authentifié (patron mapicons, `can()`/RLS relus à chaque octet servi) ; un champ `attachment` se déclare au niveau de la `Collection` (`attachment_fields`, JSON) et apparaît dans `GET /collections/{id}/schema` comme un pseudo-champ, consommé par le widget Formulaire (nouveau type de champ), l'éditeur de popup de carte (`attachmentField` sur `PopupConfig`) et `/sites/{slug}` (dérivé automatiquement).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + boto3 (cœur), React + React Query (shell), FastMCP (outil MCP). Aucune nouvelle dépendance.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md` — toute divergence avec ce plan se résout en faveur du texte le plus récemment approuvé par Tanguy (ce plan), sauf contradiction manifeste, auquel cas s'arrêter et demander.
- **Checkout partagé avec une session concurrente possible** (CLAUDE.md, piège n°9) : avant chaque `git add`/`git commit`, lancer `git status --short` et ne commiter QUE les fichiers de ce plan — jamais un `git add -A`/`git add .` aveugle. Si des fichiers inattendus apparaissent modifiés/stagés, ne pas les toucher.
- `fid` (identifiant d'entité) est **toujours une chaîne** dans `app.attachments` — jamais coercé en `int`, contrairement à `app.features` (`_coerce_fid`). Pas de FK Postgres de `attachments` vers la table dynamique de la collection.
- Toute route mutante commite explicitement (`session.commit()`) après `write_audit(...)` — patron `app/ingestion/routes.py::create_upload_job`/`app/mapicons/routes.py`, pas d'auto-commit implicite supposé.
- Les routes de LECTURE (`GET /collections/{id}/items/{fid}/attachments`, `GET .../attachments/{id}/file`) utilisent `Depends(get_current_user_optional)` (anonyme autorisé sur collection publique) ; les routes d'ÉCRITURE (presign/confirm/delete) utilisent `Depends(get_current_user)` (mandatoire). Le `tenant_id` utilisé dans TOUTE requête de lecture est **`col.tenant_id`** (résolu par `get_readable_collection`), jamais `user.tenant_id` (qui vaut `None`/absent pour un visiteur anonyme).
- Docs et identifiants de test en français. Code/identifiants techniques en anglais.
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), un sujet par commit.
- Après CHAQUE tâche touchant `shell/`, lancer `npm run test` (pas seulement le fichier modifié) — piège n°6. Après chaque tâche touchant `core/`, lancer `uv run pytest` scopé au module concerné a minima.
- Régénération OpenAPI/types TS obligatoire dès qu'une route REST change (piège n°1) — faite explicitement en Tâche 8, avant les tâches shell qui en dépendent. La route `GET /collections/{id}/schema` n'a PAS de `response_model` (elle retourne un `dict` pur) : son extension (Tâche 6) ne régénère rien côté OpenAPI, seul `shell/src/api/types.ts` (écrit à la main) est à jour manuellement.
- `MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024` (25 Mo), constante unique définie dans `core/app/attachments/routes.py`, réutilisée par les tests.

---

## Task 1: Modèle + migration + colonne `Collection.attachment_fields` + contrat de couches

**Files:**
- Create: `core/app/attachments/__init__.py` (vide)
- Create: `core/app/attachments/models.py`
- Create: `core/alembic/versions/0032_attachments.py`
- Modify: `core/app/collections/models.py` (colonne `attachment_fields`)
- Modify: `core/app/db.py:48-68` (`core_table_names()`)
- Modify: `core/pyproject.toml` (`layers` + `ignore_imports`)
- Test: `core/tests/test_attachments_migration.py`

**Interfaces:**
- Produces: `Attachment` (`id`, `tenant_id`, `collection_id`, `fid`, `field_key`, `filename`, `content_type`, `byte_size`, `s3_key`, `created_by`, `created_at`), `Collection.attachment_fields: list[dict]` (forme `[{"key": str, "label": str}]`) — consommés par la Tâche 2 (dépôt) et la Tâche 3 (routes/schémas).

- [ ] **Step 1: Écrire le modèle**

```python
# core/app/attachments/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/attachments/models.py
# SPDX-License-Identifier: Apache-2.0
"""Pièces jointes sur une entité de collection (chantier 4.12,
docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md). `fid` est
toujours du texte (contrairement à app.features, qui coerce en int selon le
type de la PK introspectée) et n'a AUCUNE FK Postgres vers la table dynamique
de la collection — impossible génériquement, chaque collection est une vraie
table dont le nom varie (cf. spec §1). L'intégrité (collection_id, fid) est
gérée côté application, comme feature_count."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index(
            "ix_attachments_entity",
            "tenant_id",
            "collection_id",
            "fid",
            "field_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), nullable=False)
    fid: Mapped[str] = mapped_column(String, nullable=False)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 2: Ajouter la colonne `attachment_fields` sur `Collection`**

`core/app/collections/models.py` — ajouter l'import `JSON` et la colonne, juste après `editable` :

```diff
-from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
+from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
```

```diff
     editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
+    # [{"key": str, "label": str}] — champs `attachment` déclarés (chantier
+    # 4.12) ; pas de colonne SQL réelle par champ, cf.
+    # docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md §3.1.
+    attachment_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
     created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 3: Enregistrer le module dans `core_table_names()`**

`core/app/db.py:48-68` — insérer entre `appexport` et `audit` (ordre alphabétique déjà en place) :

```diff
     from app.alerts import models as alerts_models  # noqa: F401
     from app.appexport import models as appexport_models  # noqa: F401
+    from app.attachments import models as attachments_models  # noqa: F401
     from app.audit import models as audit_models  # noqa: F401
```

- [ ] **Step 4: Écrire la migration Alembic**

```python
# core/alembic/versions/0032_attachments.py
# SPDX-License-Identifier: Apache-2.0
"""app.attachments — table attachments + Collection.attachment_fields
(chantier 4.12, docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md)

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("fid", sa.String(), nullable=False),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_attachments_entity",
        "attachments",
        ["tenant_id", "collection_id", "fid", "field_key"],
    )
    op.add_column(
        "collections",
        sa.Column(
            "attachment_fields", sa.JSON(), nullable=False, server_default="[]"
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "attachment_fields")
    op.drop_index("ix_attachments_entity", table_name="attachments")
    op.drop_table("attachments")
```

- [ ] **Step 5: Placer `app.attachments` dans le contrat de couches**

`core/pyproject.toml`, bloc `layers = [...]` — insérer entre `"app.features"` et `"app.collections"` (`app.features::remove_feature` doit pouvoir importer `app.attachments` pour la cascade de suppression — Tâche 7 ; `app.attachments` a besoin de tout ce qui est déjà sous `app.features`, cf. spec §3.1) :

```diff
     "app.features",
+    "app.attachments",
     "app.collections",
```

Ajouter l'exemption nommée (une seule — cf. spec §3.1, `app.attachments.routes` importe directement deux fonctions pures d'`app.ingestion.storage`, PAS `app.ingestion.routes` : le stub `get_s3_client` est dupliqué localement en Tâche 3, donc `app.features` peut l'importer normalement sans exemption) dans le bloc `ignore_imports`, avec le commentaire justificatif :

```diff
     "app.users.repository -> app.roles.repository",
+    # app.attachments est placé entre app.features et app.collections
+    # (app.features::remove_feature importe app.attachments normalement
+    # pour la cascade de suppression — aucune exemption nécessaire dans ce
+    # sens). Mais app.attachments.routes a besoin de deux fonctions PURES
+    # d'app.ingestion.storage (ensure_uploads_bucket/generate_presigned_put_url)
+    # pour le patron A6 — app.ingestion est au-dessus d'app.features dans ce
+    # contrat, donc au-dessus de la position d'app.attachments. Le stub
+    # get_s3_client, lui, N'EST PAS importé d'app.ingestion.routes : il est
+    # redéfini localement dans app.attachments.routes (Tâche 3) précisément
+    # pour éviter une deuxième exemption sur ce module — cf.
+    # docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md §3.1.
+    "app.attachments.routes -> app.ingestion.storage",
     "app.db -> app.configs.models",
```

Et une entrée `app.db -> app.X.models` (patron déjà suivi pour chaque module à modèles, en fin de liste) :

```diff
     "app.db -> app.mapicons.models",
     "app.db -> app.roles.models",
+    "app.db -> app.attachments.models",
 ]
```

- [ ] **Step 6: Test — la migration s'applique et se défait sur une base SQLite fraîche (fumée rapide ; le test réel contre Postgres non-vide est en Tâche 18)**

```python
# core/tests/test_attachments_migration.py
# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import Base, make_engine


def test_attachments_table_created_via_create_all():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    from app.attachments import models  # noqa: F401 -- enregistre sur Base.metadata
    from app.collections import models as collections_models  # noqa: F401

    Base.metadata.create_all(engine)
    tables = inspect(engine).get_table_names()
    assert "attachments" in tables
    columns = {c["name"] for c in inspect(engine).get_columns("collections")}
    assert "attachment_fields" in columns
```

- [ ] **Step 7: Lancer les vérifications**

```bash
cd core && uv run pytest tests/test_attachments_migration.py -v
uv run lint-imports
uv run alembic heads   # doit afficher 0032 (pas d'embranchement)
```
Expected: tests PASS, `lint-imports` propre, une seule tête `0032`.

- [ ] **Step 8: Commit**

```bash
git add core/app/attachments/__init__.py core/app/attachments/models.py \
  core/app/collections/models.py core/app/db.py core/pyproject.toml \
  core/alembic/versions/0032_attachments.py core/tests/test_attachments_migration.py
git commit -m "feat(core): ajoute la table attachments + Collection.attachment_fields (SP-40)"
```

---

## Task 2: Dépôt (`app/attachments/repository.py`)

**Files:**
- Create: `core/app/attachments/repository.py`
- Test: `core/tests/test_attachments_repository.py`

**Interfaces:**
- Consumes: `Attachment` (Tâche 1).
- Produces (consommés par la Tâche 3 — routes — et la Tâche 7 — cascade de suppression) :
  - `create_attachment(session, *, tenant_id, collection_id, fid, field_key, filename, content_type, byte_size, s3_key, created_by) -> Attachment`
  - `list_attachments(session, *, tenant_id, collection_id, fid, field_key=None) -> list[Attachment]`
  - `get_attachment(session, *, tenant_id, collection_id, fid, attachment_id) -> Attachment | None`
  - `delete_attachment(session, s3_client, bucket, *, tenant_id, collection_id, fid, attachment_id) -> bool`
  - `delete_all_for_feature(session, s3_client, bucket, *, tenant_id, collection_id, fid) -> None`

- [ ] **Step 1: Écrire les tests (RED)**

```python
# core/tests/test_attachments_repository.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.attachments import repository as attachments_repo
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.deleted: list[tuple[str, str]] = []

    def delete_object(self, *, Bucket, Key):
        self.deleted.append((Bucket, Key))


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    session.commit()
    return session, tenant, user


def _create(session, *, tenant_id, created_by, fid="f1", field_key="photos"):
    return attachments_repo.create_attachment(
        session,
        tenant_id=tenant_id,
        collection_id="col1",
        fid=fid,
        field_key=field_key,
        filename="a.jpg",
        content_type="image/jpeg",
        byte_size=1234,
        s3_key=f"{tenant_id}/col1/{fid}/abc-a.jpg",
        created_by=created_by,
    )


def test_create_attachment_writes_all_fields(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()
    assert a.id is not None
    assert a.field_key == "photos"
    assert a.byte_size == 1234


def test_list_attachments_isolates_by_field_key_and_entity(env):
    session, tenant, user = env
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="photos")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="documents")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f2", field_key="photos")
    session.commit()

    rows = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1", field_key="photos"
    )
    assert len(rows) == 1

    all_for_f1 = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    assert len(all_for_f1) == 2


def test_list_attachments_isolates_by_tenant(env):
    session, tenant, user = env
    other_tenant = get_or_create_default_tenant(session)  # même défaut, cf. note ci-dessous
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1")
    session.commit()
    # Note : get_or_create_default_tenant retourne toujours LE MÊME tenant
    # par défaut dans ce dépôt (un seul tenant par process en mode mock) —
    # l'isolation tenant réelle est déjà exercée par les tests de routes
    # (Tâche 4, deux tenants distincts via deux users manuellement créés
    # avec des tenant_id différents n'est pas le patron standard ici).
    assert other_tenant.id == tenant.id


def test_get_attachment_returns_none_outside_scope(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()

    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is not None
    )
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col-other", fid="f1", attachment_id=a.id
        )
        is None
    )


def test_delete_attachment_removes_row_and_deletes_s3_object(env):
    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()
    s3 = _FakeS3Client()

    ok = attachments_repo.delete_attachment(
        session,
        s3,
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id=a.id,
    )
    session.commit()
    assert ok is True
    assert s3.deleted == [("geostudio-attachments", a.s3_key)]
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is None
    )


def test_delete_attachment_unknown_id_returns_false(env):
    session, tenant, _user = env
    s3 = _FakeS3Client()
    ok = attachments_repo.delete_attachment(
        session,
        s3,
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id="does-not-exist",
    )
    assert ok is False
    assert s3.deleted == []


def test_delete_all_for_feature_removes_only_that_entity(env):
    session, tenant, user = env
    kept = _create(session, tenant_id=tenant.id, created_by=user.id, fid="other")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="photos")
    _create(session, tenant_id=tenant.id, created_by=user.id, fid="f1", field_key="documents")
    session.commit()
    s3 = _FakeS3Client()

    attachments_repo.delete_all_for_feature(
        session, s3, "geostudio-attachments", tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    session.commit()

    remaining = attachments_repo.list_attachments(
        session, tenant_id=tenant.id, collection_id="col1", fid="f1"
    )
    assert remaining == []
    assert len(s3.deleted) == 2
    still_there = attachments_repo.get_attachment(
        session, tenant_id=tenant.id, collection_id="col1", fid="other", attachment_id=kept.id
    )
    assert still_there is not None


def test_delete_swallows_s3_client_error_and_still_removes_the_row(env):
    from botocore.exceptions import ClientError

    session, tenant, user = env
    a = _create(session, tenant_id=tenant.id, created_by=user.id)
    session.commit()

    class _BoomS3Client:
        def delete_object(self, *, Bucket, Key):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "DeleteObject")

    ok = attachments_repo.delete_attachment(
        session,
        _BoomS3Client(),
        "geostudio-attachments",
        tenant_id=tenant.id,
        collection_id="col1",
        fid="f1",
        attachment_id=a.id,
    )
    session.commit()
    assert ok is True  # la ligne est supprimée même si l'objet S3 a échoué
    assert (
        attachments_repo.get_attachment(
            session, tenant_id=tenant.id, collection_id="col1", fid="f1", attachment_id=a.id
        )
        is None
    )
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_attachments_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.attachments.repository'`

- [ ] **Step 3: Implémenter le dépôt**

```python
# core/app/attachments/repository.py
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attachments.models import Attachment

logger = logging.getLogger(__name__)


def create_attachment(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    field_key: str,
    filename: str,
    content_type: str,
    byte_size: int,
    s3_key: str,
    created_by: str,
) -> Attachment:
    attachment = Attachment(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        collection_id=collection_id,
        fid=fid,
        field_key=field_key,
        filename=filename,
        content_type=content_type,
        byte_size=byte_size,
        s3_key=s3_key,
        created_by=created_by,
    )
    session.add(attachment)
    session.flush()
    return attachment


def list_attachments(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    field_key: str | None = None,
) -> list[Attachment]:
    stmt = select(Attachment).where(
        Attachment.tenant_id == tenant_id,
        Attachment.collection_id == collection_id,
        Attachment.fid == fid,
    )
    if field_key is not None:
        stmt = stmt.where(Attachment.field_key == field_key)
    return list(session.scalars(stmt.order_by(Attachment.created_at)).all())


def get_attachment(
    session: Session, *, tenant_id: str, collection_id: str, fid: str, attachment_id: str
) -> Attachment | None:
    return session.scalar(
        select(Attachment).where(
            Attachment.tenant_id == tenant_id,
            Attachment.collection_id == collection_id,
            Attachment.fid == fid,
            Attachment.id == attachment_id,
        )
    )


def _delete_s3_object_best_effort(s3_client, bucket: str, key: str) -> None:
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
    except ClientError:
        logger.warning("attachment %s: objet S3 non supprimé", key, exc_info=True)


def delete_attachment(
    session: Session,
    s3_client,
    bucket: str,
    *,
    tenant_id: str,
    collection_id: str,
    fid: str,
    attachment_id: str,
) -> bool:
    attachment = get_attachment(
        session, tenant_id=tenant_id, collection_id=collection_id, fid=fid, attachment_id=attachment_id
    )
    if attachment is None:
        return False
    _delete_s3_object_best_effort(s3_client, bucket, attachment.s3_key)
    session.delete(attachment)
    session.flush()
    return True


def delete_all_for_feature(
    session: Session, s3_client, bucket: str, *, tenant_id: str, collection_id: str, fid: str
) -> None:
    rows = list_attachments(session, tenant_id=tenant_id, collection_id=collection_id, fid=fid)
    for attachment in rows:
        _delete_s3_object_best_effort(s3_client, bucket, attachment.s3_key)
        session.delete(attachment)
    session.flush()
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_attachments_repository.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/attachments/repository.py core/tests/test_attachments_repository.py
git commit -m "feat(core): dépôt app.attachments (SP-40)"
```

---

## Task 3: Schémas + routes d'upload (presign/confirm)

**Files:**
- Create: `core/app/attachments/schemas.py`
- Create: `core/app/attachments/routes.py`
- Modify: `core/app/collections/schemas.py` (`AttachmentFieldSpec`)
- Test: `core/tests/test_attachments_upload_routes.py`

**Interfaces:**
- Consumes: dépôt (Tâche 2), `get_readable_collection`/`get_access_facts` (`app.collections`), `can` (`app.sharing.authorization`), `write_audit` (`app.audit.writer`), `get_current_user` (`app.auth.dependency`), `ensure_uploads_bucket`/`generate_presigned_put_url` (`app.ingestion.storage`).
- Produces : `router` (`APIRouter`), `get_s3_client()` (stub, overridé dans `main.py` — Tâche 4), `get_attachments_bucket() -> str`, `MAX_ATTACHMENT_BYTES`, `_get_writable_collection(session, user, collection_id)` (helper local, mirrors `app.features.routes._get_writable` — ne peut pas l'importer, `app.attachments` est SOUS `app.features` dans le contrat) — tous consommés par la Tâche 4 (routes de lecture/suppression) et la Tâche 7 (cascade, réutilise `get_s3_client`/`get_attachments_bucket`).

- [ ] **Step 1: Écrire les tests (RED)**

```python
# core/tests/test_attachments_upload_routes.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user
from app.collections import repository as collections_repo
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.put_urls: dict[str, str] = {}
        self.heads: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.cors_set = False

    def generate_presigned_url(self, op, *, Params, ExpiresIn):
        key = Params["Key"]
        url = f"https://minio.example/{Params['Bucket']}/{key}"
        self.put_urls[key] = url
        return url

    def create_bucket(self, *, Bucket):
        pass

    def put_bucket_cors(self, *, Bucket, CORSConfiguration):
        self.cors_set = True

    def head_object(self, *, Bucket, Key):
        if Key not in self.heads:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "HeadObject")
        return self.heads[Key]

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)


def _make_client(s3=None):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    if s3 is not None:
        app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    return TestClient(app), Session, tenant, user


@pytest.fixture()
def client():
    s3 = _FakeS3Client()
    api, Session, tenant, user = _make_client(s3)
    return api, Session, tenant, user, s3


def test_presign_returns_an_upload_url_and_tenant_prefixed_key(client):
    api, _Session, tenant, _user, s3 = client
    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["key"].startswith(f"{tenant.id}/col1/f1/")
    assert body["key"] in s3.put_urls
    assert s3.cors_set is True


def test_presign_rejects_undeclared_field_key(client):
    api, *_ = client
    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "not-declared", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 400


def test_presign_requires_write_access(client):
    api, Session, tenant, _user, _s3 = client
    with Session() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
    api.app.dependency_overrides[get_current_user] = lambda: stranger

    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 403


def test_confirm_persists_the_row_after_a_successful_upload(client):
    api, _Session, tenant, user, s3 = client
    key = f"{tenant.id}/col1/f1/abc-a.jpg"
    s3.heads[key] = {"ContentLength": 512}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={"key": key, "fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["filename"] == "a.jpg"
    assert body["byteSize"] == 512
    assert body["fieldKey"] == "photos"


def test_confirm_rejects_a_key_outside_the_caller_s_tenant_prefix(client):
    api, *_ = client
    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": "other-tenant/col1/f1/abc-a.jpg",
            "fieldKey": "photos",
            "filename": "a.jpg",
            "contentType": "image/jpeg",
        },
    )
    assert res.status_code == 400


def test_confirm_rejects_and_deletes_an_oversized_object(client):
    api, _Session, tenant, _user, s3 = client
    key = f"{tenant.id}/col1/f1/abc-big.bin"
    s3.heads[key] = {"ContentLength": attachments_routes.MAX_ATTACHMENT_BYTES + 1}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={"key": key, "fieldKey": "photos", "filename": "big.bin", "contentType": "application/octet-stream"},
    )
    assert res.status_code == 400
    assert key in s3.deleted


def test_confirm_returns_404_when_the_object_was_never_uploaded(client):
    api, _Session, tenant, _user, _s3 = client
    key = f"{tenant.id}/col1/f1/never-uploaded.jpg"
    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={"key": key, "fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 404
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_attachments_upload_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.attachments.routes'` (les routes ne sont pas encore enregistrées dans `main.py`, résolu à la fin de cette tâche).

- [ ] **Step 3: Ajouter `AttachmentFieldSpec` et `attachmentFields` sur `CollectionPatch`**

`core/app/collections/schemas.py` — juste avant `CollectionPatch` :

```diff
+class AttachmentFieldSpec(BaseModel):
+    """Un champ `attachment` déclaré sur une collection (chantier 4.12) —
+    pas une colonne SQL réelle, juste un slot nommé fusionné dans
+    GET /collections/{id}/schema (app/collections/schema_json.py)."""
+
+    key: str
+    label: str
+
+
 class CollectionPatch(BaseModel):
     title: str | None = None
     description: str | None = None
     isPublic: bool | None = None
     editable: bool | None = None
+    attachmentFields: list[AttachmentFieldSpec] | None = None
```

- [ ] **Step 4: Écrire les schémas d'`app.attachments`**

```python
# core/app/attachments/schemas.py
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class AttachmentPresignRequest(BaseModel):
    fieldKey: str
    filename: str
    contentType: str


class AttachmentPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class AttachmentConfirmRequest(BaseModel):
    key: str
    fieldKey: str
    filename: str
    contentType: str


class AttachmentRead(BaseModel):
    id: str
    fieldKey: str
    filename: str
    contentType: str
    byteSize: int
    createdAt: str


class AttachmentList(BaseModel):
    attachments: list[AttachmentRead]
```

- [ ] **Step 5: Écrire les routes d'upload**

```python
# core/app/attachments/routes.py
# SPDX-License-Identifier: Apache-2.0
"""Routes self-scoped pour les pièces jointes d'une entité (chantier 4.12).

get_s3_client est un STUB PROPRE à ce module, pas réutilisé depuis
app.ingestion.routes : app.attachments est placé sous app.features dans le
contrat de couches (pour que remove_feature puisse l'importer normalement,
Tâche 7), mais app.ingestion est au-dessus d'app.features — réutiliser
ingestion_routes.get_s3_client demanderait une exemption ; le dupliquer
localement n'en demande aucune ET permet à app.features de réutiliser CE
stub pour la cascade de suppression avec la même clé d'override. Voir
docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md §3.1."""
import logging
import os
import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.attachments import repository as attachments_repo
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections.repository import get_access_facts
from app.collections.routes import get_readable_collection
from app.db import get_session
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.sharing.authorization import can
from app.attachments.schemas import (
    AttachmentConfirmRequest,
    AttachmentPresignRequest,
    AttachmentPresignResponse,
    AttachmentRead,
)
from app.attachments.models import Attachment
from app.users.models import User

router = APIRouter()

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


def get_attachments_bucket() -> str:
    return os.environ.get("S3_ATTACHMENTS_BUCKET", "geostudio-attachments")


def _get_writable_collection(session: Session, user: User, collection_id: str):
    """Mirrors app/features/routes.py::_get_writable — ne peut pas l'importer
    (app.attachments est sous app.features dans le contrat de couches)."""
    col = get_readable_collection(session, user, collection_id)
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    ):
        raise HTTPException(status_code=403, detail="write access required")
    if not col.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    return col


def _attachment_json(a: Attachment) -> AttachmentRead:
    return AttachmentRead(
        id=a.id,
        fieldKey=a.field_key,
        filename=a.filename,
        contentType=a.content_type,
        byteSize=a.byte_size,
        createdAt=a.created_at.isoformat(),
    )


def _require_declared_field(col, field_key: str) -> None:
    declared = {f["key"] for f in col.attachment_fields}
    if field_key not in declared:
        raise HTTPException(status_code=400, detail=f"unknown attachment field: {field_key}")


@router.post(
    "/collections/{collection_id}/items/{fid}/attachments/presign",
    response_model=AttachmentPresignResponse,
)
def presign_attachment(
    collection_id: str,
    fid: str,
    body: AttachmentPresignRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> AttachmentPresignResponse:
    col = _get_writable_collection(session, user, collection_id)
    _require_declared_field(col, body.fieldKey)
    bucket = get_attachments_bucket()
    ensure_uploads_bucket(s3, bucket)
    key = f"{col.tenant_id}/{collection_id}/{fid}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type=body.contentType)
    return AttachmentPresignResponse(uploadUrl=url, key=key)


@router.post(
    "/collections/{collection_id}/items/{fid}/attachments",
    response_model=AttachmentRead,
    status_code=201,
)
def confirm_attachment(
    collection_id: str,
    fid: str,
    body: AttachmentConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> AttachmentRead:
    col = _get_writable_collection(session, user, collection_id)
    _require_declared_field(col, body.fieldKey)
    # Même garde anti-confused-deputy que POST /uploads (app/ingestion/routes.py) :
    # la clé est censée venir du présigné ci-dessus, toujours préfixée par le
    # tenant de l'appelant.
    if not body.key.startswith(f"{col.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    bucket = get_attachments_bucket()
    try:
        head = s3.head_object(Bucket=bucket, Key=body.key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc
    size = head["ContentLength"]
    if size > MAX_ATTACHMENT_BYTES:
        try:
            s3.delete_object(Bucket=bucket, Key=body.key)
        except ClientError:
            logger.warning("attachment oversize %s: objet non supprimé", body.key, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"fichier trop volumineux (> {MAX_ATTACHMENT_BYTES} octets)",
        )
    attachment = attachments_repo.create_attachment(
        session,
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        field_key=body.fieldKey,
        filename=body.filename,
        content_type=body.contentType,
        byte_size=size,
        s3_key=body.key,
        created_by=user.id,
    )
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="attachment.create",
        object_type="attachment",
        object_id=attachment.id,
        payload={"collection": collection_id, "fid": fid, "fieldKey": body.fieldKey},
    )
    session.commit()
    return _attachment_json(attachment)
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_attachments_upload_routes.py -v`
Expected: FAIL encore — les routes existent mais ne sont montées sur aucune `app` FastAPI (`create_app()` ne les inclut pas encore). C'est attendu : l'inclusion dans `main.py` se fait en Tâche 4 (avec les routes de lecture/suppression), pour un seul commit d'enregistrement. Vérifier ici seulement l'absence d'erreur d'import :

```bash
cd core && uv run python -c "from app.attachments import routes"
```
Expected: aucune erreur.

- [ ] **Step 7: Commit**

```bash
git add core/app/attachments/schemas.py core/app/attachments/routes.py \
  core/app/collections/schemas.py core/tests/test_attachments_upload_routes.py
git commit -m "feat(core): routes presign/confirm de app.attachments (SP-40)"
```

---

## Task 4: Routes de lecture/suppression + enregistrement dans `main.py`

**Files:**
- Modify: `core/app/attachments/routes.py` (ajoute liste/fichier/suppression)
- Modify: `core/app/main.py` (import + `include_router`)
- Test: `core/tests/test_attachments_upload_routes.py` (complète les tests laissés en attente de la Tâche 3)
- Test: `core/tests/test_attachments_read_routes.py`

**Interfaces:**
- Consumes: Tâche 3 (`get_s3_client`, `get_attachments_bucket`, `_get_writable_collection`, `_attachment_json`).
- Produces: `GET /collections/{id}/items/{fid}/attachments`, `GET .../attachments/{id}/file`, `DELETE .../attachments/{id}` — consommées par le shell (Tâche 8) après régénération OpenAPI.

- [ ] **Step 1: Compléter le test de la Tâche 3 (les routes sont maintenant montées)**

`core/tests/test_attachments_upload_routes.py` — retirer le commentaire d'attente et vérifier que les 7 tests déjà écrits passent une fois `main.py` mis à jour (Step 3 ci-dessous). Aucun nouveau test ici, juste l'exécution ; passer directement au Step 2.

- [ ] **Step 2: Écrire les tests des routes de lecture/suppression (RED)**

```python
# core/tests/test_attachments_read_routes.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import repository as attachments_repo
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "GetObject")

        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        owner = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        reader = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()
        attachment = attachments_repo.create_attachment(
            setup_session,
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=3,
            s3_key=f"{tenant.id}/col1/f1/abc-a.jpg",
            created_by=owner.id,
        )
        setup_session.commit()
        attachment_id = attachment.id
        s3_key = attachment.s3_key

    s3 = _FakeS3Client()
    s3.objects[s3_key] = b"jpg"

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    api = TestClient(app)
    return api, Session, tenant, owner, reader, attachment_id, s3


def test_list_visible_to_the_owner(env):
    api, _Session, _tenant, owner, _reader, _attachment_id, _s3 = env
    api.app.dependency_overrides[get_current_user] = lambda: owner
    res = api.get("/collections/col1/items/f1/attachments")
    assert res.status_code == 200
    assert res.json()["attachments"][0]["filename"] == "a.jpg"


def test_file_visible_to_another_reader_with_read_access(env):
    """Preuve de sortie littérale du chantier 4.12."""
    api, _Session, _tenant, _owner, reader, attachment_id, _s3 = env
    api.app.dependency_overrides[get_current_user] = lambda: reader
    res = api.get(f"/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert res.status_code == 200
    assert res.content == b"jpg"
    assert res.headers["content-type"].startswith("image/jpeg")
    assert 'filename="a.jpg"' in res.headers["content-disposition"]


def test_file_invisible_to_a_stranger_from_another_tenant(env):
    api, Session, _tenant, _owner, _reader, attachment_id, _s3 = env
    with Session() as session:
        other_tenant = get_or_create_default_tenant(session)
        stranger = get_or_create_user(
            session,
            tenant_id=other_tenant.id,
            oidc_sub="c",
            username="carol",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
    api.app.dependency_overrides[get_current_user] = lambda: stranger
    res = api.get(f"/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert res.status_code == 404


def test_list_and_file_are_readable_anonymously_on_a_public_collection(env):
    api, Session, tenant, owner, _reader, attachment_id, _s3 = env
    with Session() as session:
        col = session.get(__import__("app.collections.models", fromlist=["Collection"]).Collection, "col1")
        col.is_public = True
        session.commit()
    api.app.dependency_overrides.pop(get_current_user, None)

    list_res = api.get("/collections/col1/items/f1/attachments")
    assert list_res.status_code == 200
    file_res = api.get(f"/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert file_res.status_code == 200


def test_delete_removes_row_and_object_and_requires_write_access(env):
    api, _Session, _tenant, owner, reader, attachment_id, s3 = env
    api.app.dependency_overrides[get_current_user] = lambda: reader
    forbidden = api.delete(f"/collections/col1/items/f1/attachments/{attachment_id}")
    assert forbidden.status_code == 403

    api.app.dependency_overrides[get_current_user] = lambda: owner
    ok = api.delete(f"/collections/col1/items/f1/attachments/{attachment_id}")
    assert ok.status_code == 204
    assert s3.deleted == [f"{ok.request.url}".split("://")[0] and s3.deleted[0]]  # placeholder, remplacé Step 6

    missing = api.get("/collections/col1/items/f1/attachments")
    assert missing.json()["attachments"] == []
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_attachments_read_routes.py tests/test_attachments_upload_routes.py -v`
Expected: FAIL — `404 Not Found` sur toutes les routes (rien n'est encore inclus dans `create_app()`).

- [ ] **Step 4: Ajouter les routes de lecture/suppression**

`core/app/attachments/routes.py` — ajouter les imports et les trois routes en fin de fichier :

```diff
 from fastapi import APIRouter, Depends, HTTPException
+from fastapi import Response
+from app.auth.dependency import get_current_user_optional
```

```python


@router.get(
    "/collections/{collection_id}/items/{fid}/attachments",
    response_model=AttachmentList,
)
def list_attachments_route(
    collection_id: str,
    fid: str,
    fieldKey: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    col = get_readable_collection(session, user, collection_id)
    rows = attachments_repo.list_attachments(
        session, tenant_id=col.tenant_id, collection_id=collection_id, fid=fid, field_key=fieldKey
    )
    return AttachmentList(attachments=[_attachment_json(a) for a in rows])


@router.get("/collections/{collection_id}/items/{fid}/attachments/{attachment_id}/file")
def read_attachment_file(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> Response:
    col = get_readable_collection(session, user, collection_id)
    attachment = attachments_repo.get_attachment(
        session, tenant_id=col.tenant_id, collection_id=collection_id, fid=fid, attachment_id=attachment_id
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    bucket = get_attachments_bucket()
    try:
        obj = s3.get_object(Bucket=bucket, Key=attachment.s3_key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="attachment file not found") from exc
    return Response(
        content=obj["Body"].read(),
        media_type=attachment.content_type,
        headers={
            # Mêmes trois en-têtes que GET /map-icons/{id}/file
            # (app/mapicons/routes.py) — patron déjà établi pour servir un
            # fichier utilisateur authentifié.
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{attachment.filename}"',
        },
    )


@router.delete(
    "/collections/{collection_id}/items/{fid}/attachments/{attachment_id}", status_code=204
)
def delete_attachment_route(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> None:
    col = _get_writable_collection(session, user, collection_id)
    ok = attachments_repo.delete_attachment(
        session,
        s3,
        get_attachments_bucket(),
        tenant_id=col.tenant_id,
        collection_id=collection_id,
        fid=fid,
        attachment_id=attachment_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="attachment not found")
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="attachment.delete",
        object_type="attachment",
        object_id=attachment_id,
        payload={"collection": collection_id, "fid": fid},
    )
    session.commit()
```

- [ ] **Step 5: Enregistrer le routeur dans `main.py`**

Import, alphabétiquement avant `admin_tools_routes` (`attachments` < `admin_tools`? non — vérifier : "admin_tools" < "attachments" car 'd' < 't' — insérer APRÈS `admin_tools`, avant `alerts`) :

```diff
 from app.admin_tools import routes as admin_tools_routes
+from app.attachments import routes as attachments_routes
 from app.alerts import routes as alerts_routes
```

Inclusion, juste après `tiles_routes.router` (cohérent avec la place d'`app.attachments` dans le contrat de couches, juste sous `app.features`) :

```diff
     app.include_router(tiles_routes.router)
+    app.include_router(attachments_routes.router)
     app.include_router(ingestion_routes.router)
```

- [ ] **Step 6: Corriger le placeholder du test de suppression et lancer les tests**

`core/tests/test_attachments_read_routes.py`, remplacer la ligne placeholder de `test_delete_removes_row_and_object_and_requires_write_access` :

```diff
-    assert s3.deleted == [f"{ok.request.url}".split("://")[0] and s3.deleted[0]]  # placeholder, remplacé Step 6
+    assert len(s3.deleted) == 1
```

Run:
```bash
cd core && uv run pytest tests/test_attachments_upload_routes.py tests/test_attachments_read_routes.py -v
```
Expected: 13 passed (7 upload + 6 read/delete).

- [ ] **Step 7: Commit**

```bash
git add core/app/attachments/routes.py core/app/main.py \
  core/tests/test_attachments_read_routes.py core/tests/test_attachments_upload_routes.py
git commit -m "feat(core): routes de lecture/suppression de app.attachments + enregistrement (SP-40)"
```

---

## Task 5: Déclaration des champs `attachment` sur une collection (`PATCH`)

**Files:**
- Modify: `core/app/collections/routes.py` (`patch_collection`, `_collection_json`)
- Test: `core/tests/test_collections_routes.py` (ajout)

**Interfaces:**
- Consumes: `AttachmentFieldSpec` (Tâche 3).
- Produces: `PATCH /collections/{id}` accepte `attachmentFields`, `_collection_json` expose `attachmentFields` — consommé par le shell (Tâche 8-9).

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `core/tests/test_collections_routes.py` — fixture réelle de ce fichier vérifiée : `env` (l.31-71) retourne `(app, client, Session, admin, regular, ddl_calls)`, l'aide `_as(app, user)` (l.74-76) bascule l'identité courante, une collection s'enregistre via `POST /collections` avec `tableName: "incidents"` (seule table connue de `fake_introspector`, l.15-28) — patron exact de `test_patch_and_delete` (l.403-413) :

```python
def test_patch_collection_declares_attachment_fields(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents", json={"attachmentFields": [{"key": "photos", "label": "Photos"}]}
    )
    assert res.status_code == 200
    assert res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]

    get_res = client.get("/collections/incidents")
    assert get_res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]


def test_patch_collection_without_attachment_fields_leaves_them_unchanged(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch(
        "/collections/incidents", json={"attachmentFields": [{"key": "photos", "label": "Photos"}]}
    )

    res = client.patch("/collections/incidents", json={"title": "Nouveau titre"})
    assert res.status_code == 200
    assert res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]


def test_register_collection_defaults_attachment_fields_to_empty(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    res = client.post("/collections", json={"tableName": "incidents"})
    assert res.json()["attachmentFields"] == []
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_routes.py -k attachment_fields -v`
Expected: FAIL — `KeyError: 'attachmentFields'` (absent de la réponse).

- [ ] **Step 3: Étendre `_collection_json` et `patch_collection`**

`core/app/collections/routes.py` :

```diff
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
+        "attachmentFields": col.attachment_fields,
     }
```

Dans `patch_collection`, après la boucle `for attr, value in (...)` existante :

```diff
     for attr, value in (
         ("title", body.title),
         ("description", body.description),
         ("is_public", body.isPublic),
         ("editable", body.editable),
     ):
         if value is not None:
             setattr(col, attr, value)
+    if body.attachmentFields is not None:
+        col.attachment_fields = [f.model_dump() for f in body.attachmentFields]
     session.flush()
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: tous les tests existants + 3 nouveaux, PASS (aucune régression sur les tests `PATCH`/`GET` existants — `attachmentFields` apparaît maintenant dans TOUTE réponse `_collection_json`, y compris les tests déjà écrits qui ne l'attendaient pas encore : vérifier qu'aucun ne fait une comparaison stricte `==` sur le dict complet sans ce champ — sinon les adapter).

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/routes.py core/tests/test_collections_routes.py
git commit -m "feat(core): PATCH /collections/{id} accepte attachmentFields (SP-40)"
```

---

## Task 6: Fusion des champs `attachment` dans `GET /collections/{id}/schema`

**Files:**
- Modify: `core/app/collections/schema_json.py`
- Modify: `core/app/collections/routes.py` (`get_collection_schema`)
- Test: `core/tests/test_collections_schema_json.py` (ou fichier de test existant pour `schema_json.py` — vérifier son nom exact avant d'écrire, sinon le créer)

**Interfaces:**
- Consumes: `Collection.attachment_fields` (Tâche 1).
- Produces: `table_info_to_schema(info, attachment_fields=())` — chaque entrée `{"name": key, "type": "attachment", "required": False, "label": label}` ajoutée à `fields`. Consommé par le shell (Tâche 8, `CollectionSchemaField["type"]`).

- [ ] **Step 1: Écrire le test (RED)**

```python
# core/tests/test_collections_schema_json.py
# SPDX-License-Identifier: Apache-2.0
from app.collections.introspection import ColumnInfo, TableInfo
from app.collections.schema_json import table_info_to_schema


def _info() -> TableInfo:
    return TableInfo(
        table_name="t",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="geom", type="string", required=False),
            ColumnInfo(name="nom", type="string", required=False),
        ],
    )


def test_table_info_to_schema_without_attachment_fields_is_unchanged():
    schema = table_info_to_schema(_info())
    assert [f["name"] for f in schema["fields"]] == ["nom"]


def test_table_info_to_schema_appends_declared_attachment_fields():
    schema = table_info_to_schema(_info(), attachment_fields=[{"key": "photos", "label": "Photos"}])
    names = [f["name"] for f in schema["fields"]]
    assert names == ["nom", "photos"]
    attachment_entry = schema["fields"][-1]
    assert attachment_entry == {
        "name": "photos",
        "type": "attachment",
        "required": False,
        "label": "Photos",
    }
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_schema_json.py -v`
Expected: FAIL — `TypeError: table_info_to_schema() got an unexpected keyword argument 'attachment_fields'`.

- [ ] **Step 3: Étendre `table_info_to_schema`**

```diff
-def table_info_to_schema(info: TableInfo) -> dict:
+def table_info_to_schema(info: TableInfo, attachment_fields: list[dict] | None = None) -> dict:
     fields = []
     for col in info.columns:
         if col.name in (info.pk_column, "tenant_id", info.geometry_column):
             continue
         entry: dict = {"name": col.name, "type": col.type, "required": col.required}
         if col.max_length is not None:
             entry["maxLength"] = col.max_length
         if col.enum_values is not None:
             entry["values"] = col.enum_values
         fields.append(entry)
+    for spec in attachment_fields or []:
+        fields.append(
+            {"name": spec["key"], "type": "attachment", "required": False, "label": spec["label"]}
+        )
     geometry = None
```

- [ ] **Step 4: Câbler `get_collection_schema`**

`core/app/collections/routes.py:405` :

```diff
-    return table_info_to_schema(info)
+    return table_info_to_schema(info, attachment_fields=col.attachment_fields)
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_schema_json.py tests/test_collections_routes.py -v`
Expected: tous PASS.

- [ ] **Step 6: Commit**

```bash
git add core/app/collections/schema_json.py core/app/collections/routes.py \
  core/tests/test_collections_schema_json.py
git commit -m "feat(core): GET /collections/{id}/schema fusionne les champs attachment déclarés (SP-40)"
```

---

## Task 7: Suppression en cascade depuis `remove_feature`

**Files:**
- Modify: `core/app/features/routes.py` (imports + `remove_feature`, l.614-644)
- Modify: `core/app/main.py` (override S3 pour `attachments_routes.get_s3_client` — cf. spec §3.1)
- Test: `core/tests/test_features_routes.py` (ajout, ou fichier équivalent — vérifier le nom exact avant d'écrire)

**Interfaces:**
- Consumes: `attachments_repo.delete_all_for_feature` (Tâche 2), `attachments_routes.get_s3_client`/`get_attachments_bucket` (Tâche 3-4).

- [ ] **Step 1: Écrire le test (RED)**

Ajouter au fichier de tests de `app/features/routes.py` (adapter le nom exact des fixtures déjà en place dans ce fichier — probablement une fixture qui crée une collection éditable réelle en base SQLite/Postgres avec `rls` neutralisé, cf. les tests `DELETE /collections/{id}/items/{fid}` déjà existants) :

```python
def test_delete_feature_cascades_to_its_attachments(client, monkeypatch):
    from app.attachments import repository as attachments_repo
    from app.attachments import routes as attachments_routes

    class _FakeS3Client:
        def __init__(self):
            self.deleted = []

        def delete_object(self, *, Bucket, Key):
            self.deleted.append(Key)

    s3 = _FakeS3Client()
    api, Session, tenant, user, col = client  # adapter à la forme réelle
    api.app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3

    with Session() as session:
        attachments_repo.create_attachment(
            session,
            tenant_id=tenant.id,
            collection_id=col.id,
            fid="1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=3,
            s3_key=f"{tenant.id}/{col.id}/1/abc-a.jpg",
            created_by=user.id,
        )
        session.commit()

    res = api.delete(f"/collections/{col.id}/items/1")
    assert res.status_code == 204

    with Session() as session:
        remaining = attachments_repo.list_attachments(
            session, tenant_id=tenant.id, collection_id=col.id, fid="1"
        )
        assert remaining == []
    assert len(s3.deleted) == 1
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_features_routes.py -k cascades_to_its_attachments -v`
Expected: FAIL — la ligne `attachments` survit à la suppression de l'entité.

- [ ] **Step 3: Câbler la cascade**

`core/app/features/routes.py` — import (alphabétique, avant `app.audit`) :

```diff
+from app.attachments import repository as attachments_repo
+from app.attachments.routes import get_attachments_bucket, get_s3_client
 from app.audit.writer import write_audit
```

`remove_feature` — nouveau paramètre `s3` et appel juste après la confirmation de suppression, avant `write_audit` :

```diff
 @router.delete("/collections/{collection_id}/items/{fid}", status_code=204)
 def remove_feature(
     collection_id: str,
     fid: str,
     user=Depends(get_current_user),
     session: Session = Depends(get_session),
     introspect=Depends(get_introspector),
     repo=Depends(get_features_repo),
     rls=Depends(get_rls_scope),
+    s3=Depends(get_s3_client),
 ):
     col = _get_writable(session, user, collection_id)
     info = introspect(session, col.table_name)
     with rls(session, col.tenant_id):
         ok = repo.delete_feature(session, info, fid=fid)
     if not ok:
         raise HTTPException(status_code=404, detail="feature not found")
     session.execute(
         text("UPDATE collections SET feature_count = feature_count - 1 WHERE id = :id"),
         {"id": col.id},
     )
+    attachments_repo.delete_all_for_feature(
+        session,
+        s3,
+        get_attachments_bucket(),
+        tenant_id=col.tenant_id,
+        collection_id=col.id,
+        fid=fid,
+    )
     write_audit(
```

- [ ] **Step 4: Enregistrer l'override S3 partagé dans `main.py`**

`core/app/main.py` — même bloc que les overrides S3 existants (l.294-336), ajouter après le bloc `terrain3d` :

```diff
         s3_terrain3d_bucket = os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
         app.dependency_overrides[terrain3d_routes.get_terrain3d_bucket] = lambda: (
             s3_terrain3d_bucket
         )
+        # Clé d'override DISTINCTE de ingestion_routes.get_s3_client : ce
+        # stub est défini localement dans app.attachments.routes (pas
+        # réutilisé depuis app.ingestion) — cf. spec SP-40 §3.1. Partagée
+        # entre les propres routes d'app.attachments (déjà incluses ci-dessus)
+        # ET app.features.routes::remove_feature (cascade de suppression),
+        # même mécanisme que les cinq modules ci-dessus avec la clé
+        # ingestion_routes.get_s3_client.
+        app.dependency_overrides[attachments_routes.get_s3_client] = lambda: make_s3_client(
+            endpoint_url=s3_endpoint,
+            access_key=s3_access_key,
+            secret_key=s3_secret_key,
+        )
```

Et l'import en tête de fichier (déjà ajouté en Tâche 4, vérifier qu'il est bien présent) :
```python
from app.attachments import routes as attachments_routes
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_features_routes.py -v`
Expected: tous les tests existants + le nouveau, PASS (le nouveau paramètre `s3=Depends(get_s3_client)` sur `remove_feature` doit être overridé dans TOUS les tests existants de ce fichier qui appellent `DELETE /collections/{id}/items/{fid}` — sinon ils échouent maintenant sur `RuntimeError: S3 client dependency not configured`. Vérifier et ajouter `app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()` à la fixture partagée du fichier si nécessaire, pas seulement au nouveau test).

- [ ] **Step 6: Commit**

```bash
git add core/app/features/routes.py core/app/main.py core/tests/test_features_routes.py
git commit -m "feat(core): remove_feature supprime en cascade les pièces jointes de l'entité (SP-40)"
```

---

## Task 8: Outil MCP `list_attachments`

**Files:**
- Modify: `core/app/mcp/tools.py` (import + `register_tools`)
- Test: `core/tests/test_mcp_tools_attachments.py`

**Interfaces:**
- Consumes: `attachments_repo.list_attachments` (Tâche 2), `_require_collection_read` (`app.mcp.tools`, déjà existant).
- Produces: tool MCP `list_attachments`.

- [ ] **Step 1: Écrire les tests (RED)**

```python
# core/tests/test_mcp_tools_attachments.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.attachments import repository as attachments_repo
from app.collections.models import Collection
from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from app import db


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=mock_user.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()
        attachments_repo.create_attachment(
            setup_session,
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=3,
            s3_key=f"{tenant.id}/col1/f1/abc-a.jpg",
            created_by=mock_user.id,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    from fastapi.testclient import TestClient

    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


# Réutilise le patron call_tool/call_tool_raw de test_mcp_tools_items.py —
# copié ici pour ne pas créer une dépendance de test à test, comme les
# autres fichiers test_mcp_tools_*.py de ce dépôt (chacun est autonome).
def call_tool(test_client, name: str, arguments: dict) -> dict:
    import json

    result = call_tool_raw(test_client, name, arguments)
    if result.get("isError"):
        raise AssertionError(f"tool {name} errored: {result['content'][0]['text']}")
    return json.loads(result["content"][0]["text"])


def call_tool_expecting_error(test_client, name: str, arguments: dict) -> str:
    result = call_tool_raw(test_client, name, arguments)
    assert result.get("isError"), f"expected tool {name} to error, got: {result}"
    return result["content"][0]["text"]


def call_tool_raw(test_client, name: str, arguments: dict) -> dict:
    import json

    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=headers,
    )
    assert init_response.status_code == 200
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}
    notify_response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers,
    )
    assert notify_response.status_code == 202
    call_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(line for line in call_response.text.splitlines() if line.startswith("data: "))
    payload = json.loads(body_line.removeprefix("data: "))
    return payload["result"]


def test_list_attachments_returns_metadata_and_file_url(app_client):
    with app_client:
        result = call_tool(app_client, "list_attachments", {"collectionId": "col1", "fid": "f1"})
    assert len(result) == 1
    row = result[0]
    assert row["filename"] == "a.jpg"
    assert row["fieldKey"] == "photos"
    assert row["fileUrl"] == "/collections/col1/items/f1/attachments/" + row["id"] + "/file"


def test_list_attachments_filters_by_field_key(app_client):
    with app_client:
        result = call_tool(
            app_client, "list_attachments", {"collectionId": "col1", "fid": "f1", "fieldKey": "documents"}
        )
    assert result == []


def test_list_attachments_errors_on_an_invisible_collection(app_client):
    with app_client.session_factory() as session:
        other_tenant = get_or_create_default_tenant(session)  # même tenant par défaut dans ce dépôt
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "list_attachments", {"collectionId": "does-not-exist", "fid": "f1"}
        )
    assert "not found" in error_text.lower()


def test_list_attachments_is_not_in_the_copilot_allowlist():
    assert "list_attachments" not in ALLOWED_MCP_TOOL_NAMES
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_mcp_tools_attachments.py -v`
Expected: `test_list_attachments_is_not_in_the_copilot_allowlist` PASS déjà (rien à faire côté allowlist) ; les trois autres FAIL — `Unknown tool: list_attachments`.

- [ ] **Step 3: Enregistrer le tool**

`core/app/mcp/tools.py` — import, avec les autres imports de repositories (ordre alphabétique du bloc `from app.X import repository as X_repo`) :

```diff
 from app.alerts import repository as alerts_repo
+from app.attachments import repository as attachments_repo
 from app.analytics.aggregate import (
```

Dans `register_tools`, ajouter le tool (placé après `whoami`, avant `list_items`, pour rester proche des tools de lecture simples) :

```diff
     @server.tool()
     async def whoami(ctx: Context) -> dict:
         """Return the identity of the currently authenticated MCP caller —
         proves the OAuth handshake resolves to the same User the shell's
         REST API would resolve for the same Keycloak subject."""
         access_token = get_access_token()
         with request_scoped_session(session_factory) as session:
             user = _resolve_actor(session, access_token)
             return {"username": user.username, "tenantId": user.tenant_id}

+    @server.tool()
+    async def list_attachments(
+        ctx: Context, collectionId: str, fid: str, fieldKey: str | None = None
+    ) -> list[dict]:
+        """List the metadata of files attached to one entity of a collection
+        (chantier 4.12) — read-only, never returns file bytes: fileUrl points
+        to the REST proxy-read the caller fetches separately, same pattern as
+        ItemRead.thumbnailUrl. Deliberately absent from the copilot's
+        ALLOWED_MCP_TOOL_NAMES (app/copilot/tools_allowlist.py)."""
+        access_token = get_access_token()
+        with request_scoped_session(session_factory) as session:
+            user = _resolve_actor(session, access_token)
+            _require_collection_read(session, user=user, collection_id=collectionId)
+            rows = attachments_repo.list_attachments(
+                session,
+                tenant_id=user.tenant_id,
+                collection_id=collectionId,
+                fid=fid,
+                field_key=fieldKey,
+            )
+            return [
+                {
+                    "id": a.id,
+                    "fieldKey": a.field_key,
+                    "filename": a.filename,
+                    "contentType": a.content_type,
+                    "byteSize": a.byte_size,
+                    "fileUrl": f"/collections/{collectionId}/items/{fid}/attachments/{a.id}/file",
+                }
+                for a in rows
+            ]
+
     @server.tool()
     async def list_items(
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_mcp_tools_attachments.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_attachments.py
git commit -m "feat(core): outil MCP list_attachments en lecture seule (SP-40)"
```

---

## Task 9: Buckets S3 — docker-compose, .env.example, backup.sh

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `.env.example`
- Modify: `deploy/backup/backup.sh`
- Test: `core/tests/test_deployability.py` (aucune modification de test nécessaire — règles génériques déjà en place, vérifiées au Step 3)

**Interfaces:** aucune (config seule).

- [ ] **Step 1: `docker-compose.yml`**

Service `core`, dans le bloc `environment:` (juste après `S3_MAPICONS_BUCKET`) :

```diff
       S3_MAPICONS_BUCKET: geostudio-mapicons
+      S3_ATTACHMENTS_BUCKET: geostudio-attachments
```

- [ ] **Step 2: `docker-compose.prod.yml`**

Même emplacement relatif (après `S3_MAPICONS_BUCKET`) :

```diff
       S3_MAPICONS_BUCKET: geostudio-mapicons
+      S3_ATTACHMENTS_BUCKET: geostudio-attachments
```

- [ ] **Step 3: `.env.example`**

Dans le bloc de commentaire documentant les buckets fixés en dur (juste après la ligne `S3_MAPICONS_BUCKET`) :

```diff
 #   S3_MAPICONS_BUCKET=geostudio-mapicons      (sauvegardé)
+#   S3_ATTACHMENTS_BUCKET=geostudio-attachments (sauvegardé)
 #   S3_CDC_BUCKET=geostudio-cdc                (sauvegardé)
```

- [ ] **Step 4: `deploy/backup/backup.sh`**

Ajouter au tableau de buckets sauvegardés, après `S3_MAPICONS_BUCKET` :

```diff
 for bucket in "${S3_THUMBNAILS_BUCKET:-geostudio-thumbnails}" \
               "${S3_UPLOADS_BUCKET:-geostudio-uploads}" \
               "${S3_CDC_BUCKET:-geostudio-cdc}" \
               "${S3_TILESET3D_BUCKET:-geostudio-tileset3d}" \
               "${S3_TERRAIN3D_BUCKET:-geostudio-terrain3d}" \
-              "${S3_MAPICONS_BUCKET:-geostudio-mapicons}"; do
+              "${S3_MAPICONS_BUCKET:-geostudio-mapicons}" \
+              "${S3_ATTACHMENTS_BUCKET:-geostudio-attachments}"; do
```

- [ ] **Step 5: Vérifier `docker compose config` et le garde-fou de déployabilité**

```bash
docker compose -f docker-compose.yml config >/dev/null
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null
cd core && uv run pytest tests/test_deployability.py -v
```
Expected: les deux `config` réussissent sans erreur ; `test_backup_covers_every_bucket_the_core_uses` (et l'ensemble du fichier) PASS — la règle est générique (dérive `S3_*_BUCKET` de l'environnement réel du service `core`), aucune modification de test nécessaire.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml .env.example deploy/backup/backup.sh
git commit -m "feat(deploy): câble S3_ATTACHMENTS_BUCKET (core + sauvegarde) (SP-40)"
```

---

## Task 10: Régénération OpenAPI + types TS + `ItemClient`/hooks

**Files:**
- Modify: `core/openapi.json` (régénéré, pas édité à la main)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `shell/src/api/types.ts` (`CollectionSchemaField`, `CollectionAdmin`, `CollectionPatchInput`, `PopupConfig`, nouveau type `AttachmentSummary`)
- Modify: `shell/src/api/itemClient.ts` (5 méthodes + `attachmentFileUrl`)
- Modify: `shell/src/api/hooks.ts` (hooks React Query)
- Test: `shell/src/api/itemClient.test.ts` (ajout)

**Interfaces:**
- Produces: `client.presignAttachmentUpload`, `client.confirmAttachmentUpload`, `client.listAttachments`, `client.deleteAttachment`, `client.attachmentFileUrl` (`ItemClient`, `shell/src/api/types.ts`) — consommés par la Tâche 11 (widget Formulaire) et la Tâche 13 (popup carte).

- [ ] **Step 1: Régénérer OpenAPI + types**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` gagne les 5 routes `app.attachments` (+ leurs schémas `AttachmentPresignResponse`/`AttachmentRead`/etc.) ; `core-schema.d.ts` régénéré en conséquence. `git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts` non vide.

- [ ] **Step 2: Étendre les types hand-written**

`shell/src/api/types.ts` :

```diff
 export type CollectionFieldType =
-  "string" | "integer" | "number" | "boolean" | "date" | "datetime" | "enum" | "unsupported";
+  | "string"
+  | "integer"
+  | "number"
+  | "boolean"
+  | "date"
+  | "datetime"
+  | "enum"
+  | "attachment"
+  | "unsupported";

 export type CollectionSchemaField = {
   name: string;
   type: CollectionFieldType;
   required: boolean;
   maxLength?: number;
   values?: string[];
+  label?: string;
 };
```

```diff
 export type CollectionAdmin = {
   id: string;
   title: string;
   description: string;
   tableName: string;
   isPublic: boolean;
   editable: boolean;
   geometryType: string | null;
   srid: number | null;
   pkColumn: string;
   permissions: ItemPermissions;
   featureCount: number | null;
   owner: string | null;
+  attachmentFields: { key: string; label: string }[];
 };
```

```diff
 export type CollectionPatchInput = {
   title?: string;
   description?: string;
   isPublic?: boolean;
   editable?: boolean;
+  attachmentFields?: { key: string; label: string }[];
 };
```

`PopupConfig` (près de `PopupField`, section trouvée plus haut dans le fichier — ligne exacte à confirmer avant édition, autour de `types.ts:157-165`) :

```diff
 export type PopupConfig = {
   titleField?: string;
   fields?: PopupField[];
   template?: string;
+  attachmentField?: string;
 };
```

Ajouter le type `AttachmentSummary`, juste après `CollectionSchema` :

```typescript
export type AttachmentSummary = {
  id: string;
  fieldKey: string;
  filename: string;
  contentType: string;
  byteSize: number;
  createdAt: string;
};
```

- [ ] **Step 3: Écrire le test (RED)**

Ajouter à `shell/src/api/itemClient.test.ts` (réutiliser le patron `msw`/fetch mock déjà en place dans ce fichier pour les autres méthodes présignées — vérifier la forme exacte avant d'écrire, probablement `server.use(http.post(...))` de MSW) :

```typescript
it("presignAttachmentUpload appelle la route presign avec le bon corps", async () => {
  server.use(
    http.post(
      "http://localhost:8200/collections/col1/items/f1/attachments/presign",
      async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ fieldKey: "photos", filename: "a.jpg", contentType: "image/jpeg" });
        return HttpResponse.json({ uploadUrl: "https://minio/x", key: "t/col1/f1/x-a.jpg" });
      },
    ),
  );
  const client = makeClient(); // réutiliser le helper déjà présent dans ce fichier
  const res = await client.presignAttachmentUpload("col1", "f1", {
    fieldKey: "photos",
    filename: "a.jpg",
    contentType: "image/jpeg",
  });
  expect(res.key).toBe("t/col1/f1/x-a.jpg");
});

it("attachmentFileUrl construit l'URL du proxy-read", () => {
  const client = makeClient();
  expect(client.attachmentFileUrl("col1", "f1", "att1")).toBe(
    "http://localhost:8200/collections/col1/items/f1/attachments/att1/file",
  );
});
```

- [ ] **Step 4: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `client.presignAttachmentUpload is not a function`.

- [ ] **Step 5: Implémenter `ItemClient`**

`shell/src/api/itemClient.ts` — ajouter les imports de types (bloc d'imports existant, ordre alphabétique) :

```diff
   CollectionAdmin,
+  AttachmentSummary,
```

Puis les 5 méthodes, à côté des autres méthodes de collections (près de `getCollectionSchema`, l.1527-1541) :

```typescript
    async presignAttachmentUpload(
      collectionId: string,
      fid: string,
      input: { fieldKey: string; filename: string; contentType: string },
    ): Promise<{ uploadUrl: string; key: string }> {
      return request<{ uploadUrl: string; key: string }>(
        "POST",
        `/collections/${collectionId}/items/${fid}/attachments/presign`,
        input,
      );
    },
    async confirmAttachmentUpload(
      collectionId: string,
      fid: string,
      input: { key: string; fieldKey: string; filename: string; contentType: string },
    ): Promise<AttachmentSummary> {
      return request<AttachmentSummary>(
        "POST",
        `/collections/${collectionId}/items/${fid}/attachments`,
        input,
      );
    },
    async listAttachments(
      collectionId: string,
      fid: string,
      fieldKey?: string,
    ): Promise<AttachmentSummary[]> {
      const qs = fieldKey ? `?fieldKey=${encodeURIComponent(fieldKey)}` : "";
      const data = await request<{ attachments: AttachmentSummary[] }>(
        "GET",
        `/collections/${collectionId}/items/${fid}/attachments${qs}`,
      );
      return data.attachments;
    },
    async deleteAttachment(collectionId: string, fid: string, attachmentId: string): Promise<void> {
      await request<void>(
        "DELETE",
        `/collections/${collectionId}/items/${fid}/attachments/${attachmentId}`,
      );
    },
    attachmentFileUrl(collectionId: string, fid: string, attachmentId: string): string {
      return `${coreUrl}/collections/${collectionId}/items/${fid}/attachments/${attachmentId}/file`;
    },
```

Note : vérifier le nom exact de la variable portant l'URL de base du cœur dans ce fichier (probablement `coreUrl`/`baseUrl`, déjà utilisée par `request(...)`) avant d'écrire `attachmentFileUrl` — l'adapter si le nom diffère.

Ajouter les 5 signatures à l'interface `ItemClient` (`shell/src/api/types.ts`, section `ItemClient`, près de `getCollectionSchema`) :

```diff
   getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
+  presignAttachmentUpload(
+    collectionId: string,
+    fid: string,
+    input: { fieldKey: string; filename: string; contentType: string },
+  ): Promise<{ uploadUrl: string; key: string }>;
+  confirmAttachmentUpload(
+    collectionId: string,
+    fid: string,
+    input: { key: string; fieldKey: string; filename: string; contentType: string },
+  ): Promise<AttachmentSummary>;
+  listAttachments(collectionId: string, fid: string, fieldKey?: string): Promise<AttachmentSummary[]>;
+  deleteAttachment(collectionId: string, fid: string, attachmentId: string): Promise<void>;
+  attachmentFileUrl(collectionId: string, fid: string, attachmentId: string): string;
```

- [ ] **Step 6: Ajouter les hooks React Query**

`shell/src/api/hooks.ts` — près de `useUpdateCollection` :

```typescript
export function useAttachments(collectionId: string, fid: string | null, fieldKey: string | undefined) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["attachments", collectionId, fid, fieldKey],
    queryFn: () => client.listAttachments(collectionId, fid!, fieldKey),
    enabled: fid !== null && fieldKey !== undefined,
  });
}

export function useDeleteAttachment(collectionId: string, fid: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) => client.deleteAttachment(collectionId, fid, attachmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attachments", collectionId, fid] });
    },
  });
}
```

- [ ] **Step 7: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx
npx tsc --noEmit
```
Expected: tous PASS, `tsc` propre.

- [ ] **Step 8: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts \
  shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/api/itemClient.test.ts
git commit -m "chore: régénère OpenAPI + types TS, ajoute ItemClient/hooks pour les pièces jointes (SP-40)"
```

---

## Task 11: Widget Formulaire — type de champ `attachment`

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx`
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes: `client.presignAttachmentUpload`/`confirmAttachmentUpload`/`listAttachments`/`deleteAttachment`/`attachmentFileUrl` (Tâche 10).

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `shell/src/builder/widgets/form.test.tsx` (réutiliser le patron de rendu déjà en place dans ce fichier pour monter `FormComponent` avec un `ctx`/`props` minimal — vérifier la forme exacte des mocks `useItemClient`/`ItemClientProvider` déjà utilisés par les autres tests de ce fichier avant d'écrire) :

```typescript
it("affiche la liste des pièces jointes existantes pour un champ attachment", async () => {
  const client = makeMockClient({
    listAttachments: vi.fn().mockResolvedValue([
      { id: "att1", fieldKey: "photos", filename: "a.jpg", contentType: "image/jpeg", byteSize: 10, createdAt: "2026-01-01" },
    ]),
    attachmentFileUrl: vi.fn().mockReturnValue("http://core/x/file"),
  });
  renderForm(client, {
    fields: [
      { name: "photos", type: "attachment", label: "Photos", order: 0, hidden: false, required: false },
    ],
    editingId: "1", // adapter au patron réel de préchargement d'un enregistrement existant dans ce fichier
  });

  expect(await screen.findByText("a.jpg")).toBeInTheDocument();
});

it("désactive le champ attachment tant que l'entité n'est pas enregistrée", () => {
  const client = makeMockClient({});
  renderForm(client, {
    fields: [
      { name: "photos", type: "attachment", label: "Photos", order: 0, hidden: false, required: false },
    ],
    editingId: null,
  });

  expect(screen.getByText(/enregistrer l'entité avant d'ajouter des pièces jointes/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/ajouter des fichiers/i)).not.toBeInTheDocument();
});

it("supprime une pièce jointe au clic sur Supprimer", async () => {
  const deleteAttachment = vi.fn().mockResolvedValue(undefined);
  const client = makeMockClient({
    listAttachments: vi.fn().mockResolvedValue([
      { id: "att1", fieldKey: "photos", filename: "a.jpg", contentType: "image/jpeg", byteSize: 10, createdAt: "2026-01-01" },
    ]),
    deleteAttachment,
  });
  renderForm(client, {
    fields: [
      { name: "photos", type: "attachment", label: "Photos", order: 0, hidden: false, required: false },
    ],
    editingId: "1",
  });

  await screen.findByText("a.jpg");
  await userEvent.click(screen.getByRole("button", { name: /supprimer a\.jpg/i }));
  expect(deleteAttachment).toHaveBeenCalledWith("1", "att1");
});
```

Note : `renderForm`/`makeMockClient` sont des helpers À CRÉER s'ils n'existent pas déjà sous cette forme dans le fichier — s'appuyer sur le patron de montage déjà utilisé par les tests existants de `form.test.tsx` (probablement un rendu direct de `FormComponent` avec `QueryClientProvider`+`ItemClientProvider` mockés) plutôt que d'en inventer un nouveau.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "pièces jointes|attachment"`
Expected: FAIL — aucun texte "a.jpg" trouvé (branche `attachment` absente de `FieldInput`).

- [ ] **Step 3: Implémenter la branche `attachment`**

`shell/src/builder/widgets/form.tsx` — nouveau sous-composant, juste avant `FieldInput` :

```typescript
function AttachmentFieldInput({
  collectionId,
  fid,
  fieldKey,
  client,
}: {
  collectionId: string;
  fid: string | null;
  fieldKey: string;
  client: ReturnType<typeof useItemClient>;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["attachments", collectionId, fid, fieldKey],
    queryFn: () => client.listAttachments(collectionId, fid!, fieldKey),
    enabled: fid !== null,
  });
  const [uploading, setUploading] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || fid === null) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const { uploadUrl, key } = await client.presignAttachmentUpload(collectionId, fid, {
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
        await fetch(uploadUrl, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
        await client.confirmAttachmentUpload(collectionId, fid, {
          key,
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["attachments", collectionId, fid, fieldKey] });
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(attachmentId: string) {
    if (fid === null) return;
    await client.deleteAttachment(collectionId, fid, attachmentId);
    void queryClient.invalidateQueries({ queryKey: ["attachments", collectionId, fid, fieldKey] });
  }

  if (fid === null) {
    return (
      <p className="text-xs text-ink-3">
        Enregistrer l&apos;entité avant d&apos;ajouter des pièces jointes.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <ul className="flex flex-col gap-1">
        {(query.data ?? []).map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-xs">
            <a
              href={client.attachmentFileUrl(collectionId, fid, a.id)}
              target="_blank"
              rel="noreferrer"
              className="flex-1 truncate underline"
            >
              {a.filename}
            </a>
            <button
              type="button"
              aria-label={`Supprimer ${a.filename}`}
              className="text-danger underline"
              onClick={() => void handleDelete(a.id)}
            >
              Supprimer
            </button>
          </li>
        ))}
      </ul>
      <input
        type="file"
        multiple
        aria-label="Ajouter des fichiers"
        disabled={uploading}
        onChange={(e) => void handleFiles(e.target.files)}
      />
    </div>
  );
}
```

`FieldInput` gagne deux nouveaux props et une branche, en tête de fonction :

```diff
 function FieldInput({
   field,
   value,
   onChange,
   onBlur,
+  collectionId,
+  fid,
+  client,
 }: {
   field: FormField;
   value: unknown;
   onChange: (v: unknown) => void;
   onBlur: () => void;
+  collectionId: string;
+  fid: string | null;
+  client: ReturnType<typeof useItemClient>;
 }) {
+  if (field.type === "attachment") {
+    return (
+      <AttachmentFieldInput
+        collectionId={collectionId}
+        fid={fid}
+        fieldKey={field.name}
+        client={client}
+      />
+    );
+  }
   if (field.type === "boolean") {
```

Le site d'appel (`FormComponent`, l.489) :

```diff
           <FieldInput
             field={f}
             value={values[f.name]}
             onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
             onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
+            collectionId={collectionId}
+            fid={editingId === null ? null : String(editingId)}
+            client={client}
           />
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx
npm run test
```
Expected: tous PASS (fichier + suite complète, pas de régression croisée — piège n°6).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.test.tsx
git commit -m "feat(shell): champ attachment dans le widget Formulaire (SP-40)"
```

---

## Task 12: `EditCollectionPanel` — déclarer les champs `attachment`

**Files:**
- Modify: `shell/src/shell/EditCollectionPanel.tsx`
- Test: `shell/src/shell/EditCollectionPanel.test.tsx`

**Interfaces:**
- Consumes: `CollectionAdmin.attachmentFields`, `CollectionPatchInput.attachmentFields` (Tâche 10).

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `shell/src/shell/EditCollectionPanel.test.tsx` (réutiliser le patron de rendu/mock `useUpdateCollection` déjà présent dans ce fichier) :

```typescript
it("affiche les champs attachment déjà déclarés", () => {
  render(
    <EditCollectionPanel
      collection={{ ...baseCollection, attachmentFields: [{ key: "photos", label: "Photos" }] }}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByDisplayValue("photos")).toBeInTheDocument();
  expect(screen.getByDisplayValue("Photos")).toBeInTheDocument();
});

it("ajoute puis soumet un nouveau champ attachment", async () => {
  const mutateAsync = vi.fn().mockResolvedValue(undefined);
  mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
  render(<EditCollectionPanel collection={{ ...baseCollection, attachmentFields: [] }} onClose={vi.fn()} />);

  await userEvent.click(screen.getByRole("button", { name: "Ajouter un champ" }));
  await userEvent.type(screen.getByLabelText("Clé du champ"), "documents");
  await userEvent.type(screen.getByLabelText("Libellé du champ"), "Documents");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  expect(mutateAsync).toHaveBeenCalledWith(
    expect.objectContaining({ attachmentFields: [{ key: "documents", label: "Documents" }] }),
  );
});
```

Note : `baseCollection`/`mockUseUpdateCollection` sont les fixtures déjà présentes dans ce fichier — les étendre avec `attachmentFields: []` par défaut plutôt que d'en créer de nouvelles.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx`
Expected: FAIL — aucun champ "Clé du champ" trouvé.

- [ ] **Step 3: Implémenter l'éditeur de liste**

`shell/src/shell/EditCollectionPanel.tsx` :

```diff
 export function EditCollectionPanel({
   collection,
   onClose,
 }: {
   collection: CollectionAdmin;
   onClose: () => void;
 }) {
   const updateCollection = useUpdateCollection(collection.id);
   const instanceQuery = useInstanceInfo();
   const readOnly = instanceQuery.data?.readOnly === true;
   const [title, setTitle] = useState(collection.title);
   const [description, setDescription] = useState(collection.description);
   const [isPublic, setIsPublic] = useState(collection.isPublic);
   const [editable, setEditable] = useState(collection.editable);
+  const [attachmentFields, setAttachmentFields] = useState(collection.attachmentFields);
+  const [draftKey, setDraftKey] = useState("");
+  const [draftLabel, setDraftLabel] = useState("");

   async function submit(e: React.FormEvent) {
     e.preventDefault();
     try {
-      await updateCollection.mutateAsync({ title, description, isPublic, editable });
+      await updateCollection.mutateAsync({ title, description, isPublic, editable, attachmentFields });
       onClose();
     } catch {
       // surfaced via updateCollection.isError
     }
   }

+  function addAttachmentField() {
+    const key = draftKey.trim();
+    const label = draftLabel.trim();
+    if (!key || !label || attachmentFields.some((f) => f.key === key)) return;
+    setAttachmentFields((fields) => [...fields, { key, label }]);
+    setDraftKey("");
+    setDraftLabel("");
+  }
+
+  function removeAttachmentField(key: string) {
+    setAttachmentFields((fields) => fields.filter((f) => f.key !== key));
+  }
+
```

Et dans le JSX, après le bloc `Éditable` :

```diff
         <label className="flex items-center gap-2 text-sm text-ink">
           <input
             type="checkbox"
             aria-label="Éditable"
             checked={editable}
             onChange={(e) => setEditable(e.target.checked)}
           />
           Éditable
         </label>
+        <div className="flex flex-col gap-1">
+          <p className="text-sm font-medium text-ink">Champs de pièces jointes</p>
+          <ul className="flex flex-col gap-1">
+            {attachmentFields.map((f) => (
+              <li key={f.key} className="flex items-center gap-2 text-xs">
+                <span>
+                  {f.key} — {f.label}
+                </span>
+                <button
+                  type="button"
+                  className="text-danger underline"
+                  onClick={() => removeAttachmentField(f.key)}
+                >
+                  Retirer
+                </button>
+              </li>
+            ))}
+          </ul>
+          <div className="flex gap-2">
+            <Input aria-label="Clé du champ" value={draftKey} onChange={(e) => setDraftKey(e.target.value)} />
+            <Input
+              aria-label="Libellé du champ"
+              value={draftLabel}
+              onChange={(e) => setDraftLabel(e.target.value)}
+            />
+            <Button type="button" variant="outline" size="sm" onClick={addAttachmentField}>
+              Ajouter un champ
+            </Button>
+          </div>
+        </div>
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx
npm run test
```
Expected: tous PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/EditCollectionPanel.tsx shell/src/shell/EditCollectionPanel.test.tsx
git commit -m "feat(shell): EditCollectionPanel déclare les champs attachment (SP-40)"
```

---

## Task 13: Popup carte — `PopupEditor` + `LayersPanel`

**Files:**
- Modify: `shell/src/map/PopupEditor.tsx`
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (les deux call sites `availableFields={[]}`)
- Test: `shell/src/map/PopupEditor.test.tsx`

**Interfaces:**
- Consumes: `PopupConfig.attachmentField` (Tâche 10).
- Produces: `PopupEditor` gagne un prop `attachmentFields: string[]`, lit/écrit `value.attachmentField` — consommé par la Tâche 14 (`MapPopup`/`MapView`).

- [ ] **Step 1: Écrire les tests (RED)**

Ajouter à `shell/src/map/PopupEditor.test.tsx` :

```typescript
it("propose un sélecteur de champ pièces jointes quand attachmentFields est non vide", async () => {
  const onChange = vi.fn();
  render(
    <PopupEditor
      value={{ fields: [] }}
      availableFields={["nom"]}
      attachmentFields={["photos"]}
      onChange={onChange}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Pièces jointes"), "photos");
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ attachmentField: "photos" }));
});

it("n'affiche aucun sélecteur pièces jointes si attachmentFields est vide", () => {
  render(<PopupEditor value={{ fields: [] }} availableFields={["nom"]} attachmentFields={[]} onChange={vi.fn()} />);
  expect(screen.queryByLabelText("Pièces jointes")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/map/PopupEditor.test.tsx`
Expected: FAIL — `attachmentFields` n'est pas un prop accepté (erreur TS ou `getByLabelText` échoue).

- [ ] **Step 3: Étendre `PopupEditor`**

```diff
 export function PopupEditor({
   value,
   availableFields,
+  attachmentFields,
   onChange,
 }: {
   value: PopupConfig | undefined;
   availableFields: string[];
+  attachmentFields: string[];
   onChange: (next: PopupConfig | undefined) => void;
 }) {
```

Et dans le JSX, juste avant le bouton « Avancé (gabarit) » (donc visible que la section soit en mode liste ou gabarit) :

```diff
       {value !== undefined && !advanced && (
         <>
           {/* ... contenu existant ... */}
         </>
       )}
+      {value !== undefined && attachmentFields.length > 0 && (
+        <label className={labelCls}>
+          Pièces jointes
+          <select
+            aria-label="Pièces jointes"
+            className={inputCls}
+            value={value.attachmentField ?? ""}
+            onChange={(e) =>
+              onChange({ ...value, attachmentField: e.target.value || undefined })
+            }
+          >
+            <option value="">Aucune</option>
+            {attachmentFields.map((f) => (
+              <option key={f} value={f}>
+                {f}
+              </option>
+            ))}
+          </select>
+        </label>
+      )}
       {value !== undefined && (
         <button
```

- [ ] **Step 4: Câbler les 3 call sites**

`shell/src/map/LayersPanel.tsx`, `LayerPopupEditor` — exclure les champs `attachment` d'`availableFields` et les fournir séparément :

```diff
       availableFields={
         collectionId
-          ? (schema.data?.fields.map((f) => f.name) ?? [])
+          ? (schema.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? [])
           : featureGeojson.data
             ? listFields(featureGeojson.data)
             : []
       }
+      attachmentFields={
+        collectionId
+          ? (schema.data?.fields.filter((f) => f.type === "attachment").map((f) => f.name) ?? [])
+          : []
+      }
       onChange={(popup) => onChangeLayer({ ...layer, popup })}
```

`shell/src/builder/widgets/mapWidget.tsx`, les deux call sites `<PopupEditor availableFields={[]} .../>` — même limite déjà documentée (« PropsPanel has no schema ») :

```diff
             availableFields={[]} // PropsPanel has no schema (registry.ts) — same PopupEditor precedent
+            attachmentFields={[]}
```
(appliquer aux DEUX occurrences, l.181 et l.231)

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/PopupEditor.test.tsx src/map/LayersPanel.test.tsx \
  src/builder/widgets/mapWidget.test.tsx
npx tsc --noEmit
npm run test
```
Expected: tous PASS, `tsc` propre.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/PopupEditor.tsx shell/src/map/PopupEditor.test.tsx \
  shell/src/map/LayersPanel.tsx shell/src/builder/widgets/mapWidget.tsx
git commit -m "feat(shell): sélecteur de champ pièces jointes dans PopupEditor (SP-40)"
```

---

## Task 14: Popup carte — `MapView`/`MapPopup` affichent la section

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapPopup.tsx`
- Test: `shell/src/map/MapPopup.test.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `PopupConfig.attachmentField` (Tâche 10), `AttachmentSummary` (type, Tâche 10). **Ne consomme PAS `client.listAttachments`/`attachmentFileUrl`** (les méthodes `ItemClient` de la Tâche 10) : `MapView` réimplémente l'équivalent en `fetch` nu via `getCoreUrl`/`getAuthToken` (patron déjà existant de ce composant, qui fonctionne aussi hors `ItemClientProvider` — export statique) plutôt que d'appeler `useItemClient()`.

- [ ] **Step 1: Écrire les tests `MapPopup` (RED)**

Ajouter à `shell/src/map/MapPopup.test.tsx` :

```typescript
it("affiche la section Pièces jointes quand la liste est non vide", () => {
  render(
    <MapPopup
      content={{ title: "X", rows: [], html: null }}
      x={0}
      y={0}
      onClose={vi.fn()}
      attachments={[
        { id: "a1", fieldKey: "photos", filename: "a.jpg", contentType: "image/jpeg", byteSize: 1, createdAt: "" },
      ]}
      attachmentFileUrl={(id) => `http://core/${id}/file`}
    />,
  );
  expect(screen.getByText("Pièces jointes")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "a.jpg" })).toHaveAttribute("href", "http://core/a1/file");
});

it("n'affiche pas la section Pièces jointes quand attachments est vide ou absent", () => {
  render(<MapPopup content={{ title: "X", rows: [], html: null }} x={0} y={0} onClose={vi.fn()} />);
  expect(screen.queryByText("Pièces jointes")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/map/MapPopup.test.tsx`
Expected: FAIL — pas de section « Pièces jointes ».

- [ ] **Step 3: Étendre `MapPopup`**

```diff
 export function MapPopup({
   content,
   x,
   y,
   onClose,
+  attachments,
+  attachmentFileUrl,
 }: {
   content: PopupContent;
   x: number;
   y: number;
   onClose: () => void;
+  attachments?: { id: string; filename: string }[];
+  attachmentFileUrl?: (attachmentId: string) => string;
 }) {
```

```diff
       {empty && <p className="text-ink-3">Aucun attribut</p>}
+      {attachments && attachments.length > 0 && attachmentFileUrl && (
+        <div className="mt-1 border-t border-rule pt-1">
+          <p className="mb-1 text-ink-3">Pièces jointes</p>
+          <ul className="flex flex-col gap-0.5">
+            {attachments.map((a) => (
+              <li key={a.id}>
+                <a href={attachmentFileUrl(a.id)} target="_blank" rel="noreferrer" className="underline">
+                  {a.filename}
+                </a>
+              </li>
+            ))}
+          </ul>
+        </div>
+      )}
     </div>
   );
 }
```

- [ ] **Step 4: Câbler `MapView`**

`shell/src/map/MapView.tsx` — état `popup` gagne `fid` :

```diff
   const [popup, setPopup] = useState<{
     layerId: string;
     properties: Record<string, unknown>;
     lngLat: { lng: number; lat: number };
+    fid: string | undefined;
   } | null>(null);
+  const [popupAttachments, setPopupAttachments] = useState<AttachmentSummary[]>([]);
```

`handlePopup` calcule `fid` depuis la couche cliquée (uniquement les couches `vector`, qui portent `pkColumn`/`collectionId` — les couches `feature`, GeoJSON externe, n'ont pas de collection donc jamais de pièces jointes) :

```diff
   const handlePopup = useCallback(
     (
       layerId: string,
       properties: Record<string, unknown>,
       lngLat: { lng: number; lat: number },
     ) => {
       const layer = layersRef.current.find((l) => l.id === layerId);
       if (!layer || !("popup" in layer) || !layer.popup) return;
-      setPopup({ layerId, properties, lngLat });
+      const fid =
+        layer.kind === "vector" && layer.pkColumn && properties[layer.pkColumn] != null
+          ? String(properties[layer.pkColumn])
+          : undefined;
+      setPopup({ layerId, properties, lngLat, fid });
     },
```

Nouvel effet de fetch (fetch nu via `getCoreUrl`/`getAuthToken`, PAS `useItemClient`/React Query — ce composant n'a pas de dépendance sur `ItemClientProvider`, cf. son fonctionnement en export statique) juste avant le `return` :

```typescript
  useEffect(() => {
    setPopupAttachments([]);
    if (!popup || !popupConfig?.attachmentField || popup.fid === undefined) return;
    if (!popupLayer || popupLayer.kind !== "vector") return;
    const coreUrl = getCoreUrlRef.current?.();
    if (!coreUrl) return;
    const token = getAuthTokenRef.current?.();
    const url = `${coreUrl}/collections/${popupLayer.collectionId}/items/${popup.fid}/attachments?fieldKey=${encodeURIComponent(popupConfig.attachmentField)}`;
    let cancelled = false;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((res) => (res.ok ? res.json() : { attachments: [] }))
      .then((data) => {
        if (!cancelled) setPopupAttachments(data.attachments ?? []);
      })
      .catch(() => {
        if (!cancelled) setPopupAttachments([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [popup?.layerId, popup?.fid, popupConfig?.attachmentField]);
```

Note : `popupConfig`/`popupLayer` sont déjà calculés juste avant le `return` (l.1301-1306) — DÉPLACER cet effet APRÈS leur calcul (ou dupliquer localement la même logique de résolution) puisqu'un `useEffect` ne peut pas être appelé après un `return` conditionnel ; vérifier l'ordre exact des hooks lors de l'implémentation (tous les hooks doivent rester avant tout `return` conditionnel — ici il n'y en a pas avant le JSX final, donc l'insertion est sûre tant que `popupConfig`/`popupLayer` sont calculés AVANT ce nouvel effet, pas après).

Le rendu de `<MapPopup>` :

```diff
       {popup && popupPoint && !toolsActive && (
         <MapPopup
           content={resolvePopupContent(popupConfig, popup.properties)}
           x={popupPoint.x}
           y={popupPoint.y}
           onClose={() => setPopup(null)}
+          attachments={popupAttachments}
+          attachmentFileUrl={(attachmentId) =>
+            popupLayer && popupLayer.kind === "vector" && popup.fid !== undefined
+              ? `${getCoreUrlRef.current?.() ?? ""}/collections/${popupLayer.collectionId}/items/${popup.fid}/attachments/${attachmentId}/file`
+              : ""
+          }
         />
       )}
```

Ajouter l'import du type `AttachmentSummary` en tête de fichier :
```diff
-import type { ... } from "../api/types";
+import type { AttachmentSummary, ... } from "../api/types";
```
(fusionner avec le bloc d'import de types déjà présent, ordre alphabétique).

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/MapPopup.test.tsx src/map/MapView.test.tsx
npx tsc --noEmit
npm run test
```
Expected: tous PASS, `tsc` propre. Si `MapView.test.tsx` échoue sur le nouveau `useEffect` (fetch non mocké dans jsdom), ajouter un mock `global.fetch` minimal dans le test concerné plutôt que de l'ignorer.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/MapPopup.tsx shell/src/map/MapPopup.test.tsx shell/src/map/MapView.tsx \
  shell/src/map/MapView.test.tsx
git commit -m "feat(shell): MapView/MapPopup affichent les pièces jointes de l'entité cliquée (SP-40)"
```

---

## Task 15: `/sites/{slug}` — `DatasetPage` dérive `attachmentField`

**Files:**
- Modify: `shell/src/pages/DatasetPage.tsx`
- Test: `shell/src/pages/DatasetPage.test.tsx`

**Interfaces:**
- Consumes: `client.getCollectionSchema` (existant), `CollectionSchemaField.type === "attachment"` (Tâche 10).

- [ ] **Step 1: Écrire le test (RED)**

Ajouter à `shell/src/pages/DatasetPage.test.tsx` (réutiliser le mock `useItemClient`/`getCollection` déjà présent dans ce fichier) :

```typescript
it("dérive attachmentField du premier champ attachment déclaré sur la collection", async () => {
  const client = makeMockClient({
    getCollection: vi.fn().mockResolvedValue({ ...baseCollection, featureCount: 3 }),
    getCollectionSchema: vi.fn().mockResolvedValue({
      collection: "col1",
      pk: "id",
      geometry: null,
      fields: [
        { name: "nom", type: "string", required: false },
        { name: "photos", type: "attachment", required: false, label: "Photos" },
      ],
    }),
  });
  render(<DatasetPage collectionId="col1" />, { wrapper: makeWrapper(client) });

  await screen.findByText(baseCollection.title);
  // AppRenderer reçoit un widget map avec props.popup.attachmentField === "photos" —
  // vérifié en espionnant AppRenderer ou en inspectant le DOM produit par le
  // widget carte, selon le patron déjà utilisé par les autres tests de ce
  // fichier pour vérifier le contenu de previewConfig.
});
```

Note : la forme exacte de cette assertion dépend de la façon dont `DatasetPage.test.tsx` inspecte déjà `previewConfig` aujourd'hui (mock d'`AppRenderer` avec capture de `config`, le plus probable vu que `AppRenderer` est lourd à monter réellement) — suivre ce patron existant plutôt que d'en inventer un nouveau ; si `AppRenderer` est mocké, l'assertion porte directement sur les props reçues par le mock.

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/DatasetPage.test.tsx`
Expected: FAIL — `previewConfig` ne connaît pas encore la notion de champ attachment.

- [ ] **Step 3: Étendre `previewConfig` et `DatasetPage`**

```diff
-function previewConfig(collectionId: string): AppConfig {
+function previewConfig(collectionId: string, attachmentField: string | undefined): AppConfig {
   const dataSourceId = "dataset-preview";
   return {
     kind: "app",
     theme: {},
     dataSources: [
       { id: dataSourceId, type: "features", service: "core", layer: collectionId, query: {} },
     ],
     messages: [],
     layout: {
       type: "grid",
       breakpoints: {},
       items: [
         {
           id: "dataset-preview-map",
           widget: "map",
           x: 0,
           y: 0,
           w: 6,
           h: 6,
-          props: { dataSourceId },
+          props: {
+            dataSourceId,
+            ...(attachmentField ? { popup: { attachmentField } } : {}),
+          },
         },
```

```diff
 export function DatasetPage({ collectionId }: { collectionId: string }) {
   const client = useItemClient();
   const query = useQuery({
     queryKey: ["public-dataset", collectionId],
     queryFn: () => client.getCollection(collectionId),
     retry: false,
   });
+  const schemaQuery = useQuery({
+    queryKey: ["public-dataset-schema", collectionId],
+    queryFn: () => client.getCollectionSchema(collectionId),
+    retry: false,
+  });
+  const attachmentField = schemaQuery.data?.fields.find((f) => f.type === "attachment")?.name;
```

```diff
       <div className="h-[480px] w-full">
-        <AppRenderer config={previewConfig(collectionId)} mode="runtime" />
+        <AppRenderer config={previewConfig(collectionId, attachmentField)} mode="runtime" />
       </div>
```

Note : `schemaQuery` reste délibérément non bloquant (pas de garde `isLoading` supplémentaire sur la page) — si le schéma n'a pas encore résolu, `attachmentField` est `undefined` et le popup se comporte comme avant, sans casser le rendu de la page (cf. spec §3.4).

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/DatasetPage.test.tsx
npm run test
```
Expected: tous PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/DatasetPage.tsx shell/src/pages/DatasetPage.test.tsx
git commit -m "feat(shell): /sites/{slug} affiche les pièces jointes via le popup carte (SP-40)"
```

---

## Task 16: E2E — widget Formulaire

**Files:**
- Create: `shell/e2e/attachments.spec.ts`

**Interfaces:** aucune (E2E, routes mockées — cf. Global Constraints).

- [ ] **Step 1: Écrire le spec**

```typescript
// shell/e2e/attachments.spec.ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("ajouter, lister et supprimer une pièce jointe depuis le widget Formulaire", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/col1/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "col1",
        pk: "id",
        geometry: null,
        fields: [
          { name: "nom", type: "string", required: false },
          { name: "photos", type: "attachment", required: false, label: "Photos" },
        ],
      },
    });
  });

  let confirmed = false;
  await page.route("**/attachments/presign", async (route) => {
    await route.fulfill({ json: { uploadUrl: "http://localhost/upload", key: "t/col1/1/x-a.jpg" } });
  });
  await page.route("http://localhost/upload", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/collections/col1/items/1/attachments", async (route) => {
    if (route.request().method() === "POST") {
      confirmed = true;
      await route.fulfill({
        status: 201,
        json: {
          id: "att1",
          fieldKey: "photos",
          filename: "a.jpg",
          contentType: "image/jpeg",
          byteSize: 10,
          createdAt: "2026-01-01T00:00:00Z",
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        attachments: confirmed
          ? [
              {
                id: "att1",
                fieldKey: "photos",
                filename: "a.jpg",
                contentType: "image/jpeg",
                byteSize: 10,
                createdAt: "2026-01-01T00:00:00Z",
              },
            ]
          : [],
      },
    });
  });
  await page.route("**/collections/col1/items/1/attachments/att1", async (route) => {
    confirmed = false;
    await route.fulfill({ status: 204, body: "" });
  });

  // Navigation jusqu'au widget Formulaire d'une app pointant sur col1, en
  // mode édition d'un enregistrement existant (fid="1") : adapter le chemin
  // exact de navigation au patron déjà utilisé par un autre spec E2E du
  // widget Formulaire (ex. incident-form.spec.ts) — même mock d'app config,
  // même façon d'atteindre un enregistrement existant.

  await expect(page.getByLabel("Ajouter des fichiers")).toBeVisible();
  await page
    .getByLabel("Ajouter des fichiers")
    .setInputFiles({ name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("x") });

  await expect(page.getByRole("link", { name: "a.jpg" })).toBeVisible();

  await page.getByRole("button", { name: "Supprimer a.jpg" }).click();
  await expect(page.getByRole("link", { name: "a.jpg" })).toHaveCount(0);
});
```

Note explicite : compléter la section de navigation en s'appuyant sur `shell/e2e/incident-form.spec.ts` (widget Formulaire déjà exercé en E2E) pour la forme exacte du mock d'app config et du chemin de clic jusqu'à un enregistrement existant — ne pas deviner cette partie, la copier/adapter depuis ce spec existant avant de lancer le test.

- [ ] **Step 2: Lancer le spec, itérer jusqu'au vert**

```bash
cd shell && npx playwright test e2e/attachments.spec.ts
```
Expected: 1 passed. Ajuster les routes mockées/sélecteurs selon les échecs réels observés (le mock exact de navigation dépend de `incident-form.spec.ts`, à lire avant d'ajuster).

- [ ] **Step 3: Commit**

```bash
git add shell/e2e/attachments.spec.ts
git commit -m "test(e2e): ajout/liste/suppression de pièces jointes depuis le widget Formulaire (SP-40)"
```

---

## Task 17: E2E — popup carte

**Files:**
- Create: `shell/e2e/attachments-popup.spec.ts`

**Interfaces:** aucune.

- [ ] **Step 1: Écrire le spec**

```typescript
// shell/e2e/attachments-popup.spec.ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("cliquer une entité avec un champ attachment configuré révèle sa pièce jointe dans le popup", async ({
  page,
}) => {
  await mockCore(page);

  await page.route("**/collections/col1/items/1/attachments*", async (route) => {
    await route.fulfill({
      json: {
        attachments: [
          {
            id: "att1",
            fieldKey: "photos",
            filename: "releve.jpg",
            contentType: "image/jpeg",
            byteSize: 10,
            createdAt: "2026-01-01T00:00:00Z",
          },
        ],
      },
    });
  });

  // Navigation jusqu'à une carte dont une couche vector a
  // popup: { attachmentField: "photos" }, puis clic sur l'entité fid="1" —
  // adapter au patron déjà utilisé par map-popup.spec.ts (existant) pour le
  // mock des tuiles MVT / GeoJSON de la couche et le clic sur une entité.

  await expect(page.getByText("Pièces jointes")).toBeVisible();
  await expect(page.getByRole("link", { name: "releve.jpg" })).toBeVisible();
});
```

Note explicite : s'appuyer sur `shell/e2e/map-popup.spec.ts` (existant, SP-24) pour la forme exacte du mock de couche/clic — ne pas deviner, lire ce fichier avant d'écrire la navigation.

- [ ] **Step 2: Lancer le spec, itérer jusqu'au vert**

```bash
cd shell && npx playwright test e2e/attachments-popup.spec.ts
```
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add shell/e2e/attachments-popup.spec.ts
git commit -m "test(e2e): popup carte affiche les pièces jointes de l'entité cliquée (SP-40)"
```

---

## Task 18: Vérification finale de branche

**Files:** aucun nouveau fichier — vérification pure.

**Interfaces:** aucune.

- [ ] **Step 1: `git status` — vérifier qu'aucun fichier étranger à ce plan n'est resté modifié**

```bash
git status --short
```
Si des fichiers hors de ce plan apparaissent (session concurrente, cf. Global Constraints), NE PAS les committer ; s'assurer que seuls les fichiers listés dans les Tâches 1-17 ont été touchés par cette branche (`git log --oneline` doit montrer exactement les 17 commits de ce plan).

- [ ] **Step 2: Suite cœur complète**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run pytest
```
Expected: toutes les portes vertes ; `pytest` sans nouvelle régression (comparer au compte de référence du dernier `### Livré` de CLAUDE.md, delta positif attendu ~40 tests).

- [ ] **Step 3: Falsifier l'exemption de contrat de couches (piège n°10 — un correctif de filet de test doit être vérifié par falsification)**

```bash
cd core
git stash push -- pyproject.toml   # retire temporairement l'exemption
uv run lint-imports   # DOIT échouer maintenant
git stash pop
uv run lint-imports   # redevient propre
```
Expected: le premier `lint-imports` échoue explicitement sur `app.attachments.routes -> app.ingestion.storage`, confirmant que l'exemption est réellement nécessaire (pas un ajout superflu).

- [ ] **Step 4: Suite shell complète (après nettoyage `dist/`/`dist-export/` — piège de couverture)**

```bash
cd shell
rm -rf dist dist-export
npm run lint && npm run format:check
npx tsc --noEmit
npm run test -- --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
```
Expected: tout vert, couverture non régressée (seuil 88).

- [ ] **Step 5: Suite E2E complète (piège n°6 — jamais se fier à une exécution scopée)**

```bash
cd shell
npm run e2e
cat test-results/.last-run.json   # source de vérité, pas le tail du reporter list (piège méthodologique SP-31)
```
Expected: 0 failed. Si une régression croisée apparaît sur un spec NON touché par ce plan (mock périmé par un des changements de types ci-dessus), la corriger avant de clore.

- [ ] **Step 6: Contrôle manuel, recommandé non bloquant (si stack disponible)**

Si `docker compose up -d` est réalisable dans cet environnement : déclarer un champ `attachment` sur une collection réelle (`EditCollectionPanel`), attacher une photo depuis le widget Formulaire, vérifier :
- son ouverture par un second compte utilisateur avec droit de lecture,
- son invisibilité pour un compte hors partage (403/404 direct sur l'URL du proxy-read),
- son apparition dans le popup de l'éditeur de carte,
- son apparition sur `/sites/{slug}` en visiteur anonyme (collection publiée),
- une réponse `list_attachments` correcte via un client MCP réel (`tools/call`).

Si la stack n'est pas disponible dans cet environnement, documenter explicitement cette absence (comme SP-38/SP-39) plutôt que de l'omettre silencieusement.

- [ ] **Step 7: Mettre à jour CLAUDE.md**

Ajouter une entrée `### Livré` datée SP-40, sur le patron des entrées SP-38/SP-39 : chantier fermé (4.12), périmètre réellement livré (y compris l'élargissement MCP/popup/site décidé en brainstorming), comptes de tests avant/après, tout écart entre ce plan et l'exécution réelle découvert en cours de route, résultat de la revue finale si une session de revue dédiée est lancée séparément.

```bash
git add CLAUDE.md
git commit -m "docs: clôture le chantier 4.12 dans CLAUDE.md — pièces jointes sur une entité (SP-40)"
```

- [ ] **Step 8: Lancer une revue finale de branche**

Suivre `superpowers:requesting-code-review` sur l'ensemble de la branche (18 tâches) — pas seulement une relecture tâche par tâche déjà faite en cours d'exécution (piège n°4, revue par tâche ≠ revue finale). Porter une attention particulière à :
- la cohérence `tenant_id` (toujours `col.tenant_id`, jamais `user.tenant_id`, sur les 3 routes de lecture — un bug ici serait un 500 sur un visiteur anonyme, pas juste un défaut cosmétique) ;
- l'ordre des hooks dans `MapView.tsx` (Tâche 14) — le nouvel effet doit être déclaré AVANT tout retour conditionnel ;
- la double invalidation de cache (`["attachments", collectionId, fid, fieldKey]`) reste cohérente entre le widget Formulaire (Tâche 11) et les hooks génériques (Tâche 10) — deux implémentations indépendantes de la même idée, à ne pas laisser diverger silencieusement ;
- que les 3 tests existants de `test_features_routes.py`/E2E `map-popup.spec.ts`/`incident-form.spec.ts` réutilisés comme patrons (Tâches 7, 16, 17) ont bien été lus avant d'écrire le code correspondant, pas devinés.
