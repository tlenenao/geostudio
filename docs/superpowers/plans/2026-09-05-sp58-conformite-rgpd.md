# SP-58 — Conformité : quotas par tenant & droit à l'effacement (RGPD) : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-73/GAP-11 (aucun quota par tenant, ni de nombre
d'items/collections ni de stockage) et GAP-74 (aucun mécanisme de purge de
données ni de droit à l'effacement RGPD), dans cet ordre : d'abord la
mesure et l'application de quotas, puis l'anonymisation d'un utilisateur,
puis la purge complète d'un tenant — du moins destructeur (comptages,
lecture seule) au plus destructeur (suppression irréversible de toutes les
données d'un tenant).

**Rappel de priorité (spec §0, ne pas l'ignorer)** : ce chantier est noté
par la feuille de route révisée comme *« pertinent dès qu'un tenant réel
autre que l'opérateur est onboardé »* — question produit Q2 encore ouverte.
Ce plan est exécuté sur demande explicite, indépendamment de cette
priorité relative ; livrer ce plan ne tranche pas Q2.

**Architecture:** 10 tâches, en deux volets :
- **Volet A — Quotas et usage (GAP-73/GAP-11)**, Tâches 1-5.
- **Volet B — Droit à l'effacement (GAP-74)**, Tâches 6-10, elles-mêmes en
  deux opérations distinctes : anonymisation d'un utilisateur (Tâches 6-8,
  réversible dans son effet limité) puis purge complète d'un tenant
  (Tâches 9-10, irréversible — construite en dernier, sur les fondations
  des tâches précédentes : privilège dédié de la Tâche 8, `purge_receipts`
  de la Tâche 6).

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest + boto3
(cœur), TypeScript/React + Vitest + Playwright (shell), procrastinate
(job de purge asynchrone).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp58-conformite-rgpd-design.md` (toutes
sections — c'est une spec complète, pas un inventaire ; les décisions
ouvertes de son §6 sont reprises explicitement dans les tâches
correspondantes ci-dessous).

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche pose son filet de test avant
  de toucher le code de production qu'elle protège.
- Commits **conventional**, un sujet par commit, français
  (`feat(core): ...`, `test(core): ...`, `feat(shell): ...`).
- **Suite complète rejouée avant de clore chaque tâche** (piège CLAUDE.md
  n°6) : `cd core && uv run pytest`, `cd shell && npm run test` ; `npm run
  e2e` pour les tâches qui touchent une route/UI observable (Tâches 3, 4,
  5, 7, 10).
- **Toute migration testée sur base non vide, dans les deux sens** (piège
  CLAUDE.md n°8).
- **Tout filet de test ajouté est vérifié par falsification** (piège
  CLAUDE.md n°10) : injecter le défaut visé, confirmer l'échec, retirer.
- **Régénérer la spec OpenAPI + types TS dès qu'une route ou un modèle de
  réponse change** (piège CLAUDE.md n°1) — concerne les Tâches 3, 4, 5, 7,
  10.
- **Ne pas deviner un nom de fonction/fichier/ligne cité par la spec** :
  chaque tâche qui s'appuie sur un repère de la spec commence par une
  commande de vérification (`grep`/`sed`) avant d'écrire du code — la spec
  elle-même le rappelle à plusieurs endroits (§3.1.2, §3.3).
- **Câblage réel, pas seulement documenté** (piège CLAUDE.md n°2) : toute
  nouvelle variable d'environnement (`CORE_QUOTAS_ENABLED`,
  `CORE_QUOTA_MAX_ITEMS_PER_TENANT`, `CORE_QUOTA_MAX_COLLECTIONS_PER_
  TENANT`, `CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT`) doit apparaître dans
  `docker-compose.yml` (`environment:` du service `core`), `.env.example`,
  et passer `core/tests/test_deployability.py` (`test_every_core_env_var_
  is_wired_to_a_service`, `test_every_compose_substitution_is_
  documented`) avant de clore la tâche qui l'introduit.
- **Conteneur `postgis-test` non tracké par Alembic** : après chaque
  migration de ce plan, un `ALTER TABLE` manuel peut être nécessaire sur ce
  conteneur avant de rejouer la suite.
- **Aucune de ces fonctionnalités n'est exposée par MCP** (spec §2.2,
  décision explicite) — vérifier en clôture de plan qu'aucun outil MCP
  n'a été ajouté par erreur d'assemblage entre tâches.

---

## Volet A — Quotas et usage

## Task 1 : service de comptage par tenant (items, collections, utilisateurs)

Le plus simple et le moins risqué : des `COUNT(*)` filtrés `tenant_id`,
aucune migration, aucun changement de comportement observable en dehors
d'un nouveau module interne.

**Files:**
- Create: `core/app/quotas/__init__.py`, `core/app/quotas/service.py`
- Create: `core/tests/test_quotas_service.py`

**Interfaces:**
- Consumes: `app.items.models.Item`, `app.collections.models.Collection`,
  `app.users.models.User` (colonnes `tenant_id` déjà présentes sur les
  trois, vérifiées §1.1 de la spec).
- Produces: `count_items_for_tenant`, `count_collections_for_tenant`,
  `count_users_for_tenant` — consommées par la Tâche 3 (`GET /admin/
  usage`) et la Tâche 5 (garde à la création).

- [ ] **Step 1 : écrire le test avant le code**

```python
# core/tests/test_quotas_service.py
def test_count_items_for_tenant_counts_only_this_tenant(session, ...):
    # créer 2 items tenant A, 1 item tenant B
    # assert count_items_for_tenant(session, "tenant-a") == 2
```

Répéter le patron pour `count_collections_for_tenant` et
`count_users_for_tenant` (un utilisateur au moins existe déjà par tenant
dans les fixtures de test existantes — réutiliser le patron de fixture
d'un test de module voisin, ex. `core/tests/test_roles_routes.py`, à
lire avant d'écrire les fixtures de ce test plutôt que d'en réinventer un
autre).

- [ ] **Step 2 : implémenter**

```python
# core/app/quotas/service.py
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.items.models import Item
from app.users.models import User


def count_items_for_tenant(session: Session, tenant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(Item).where(Item.tenant_id == tenant_id)
    ) or 0


def count_collections_for_tenant(session: Session, tenant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(Collection).where(Collection.tenant_id == tenant_id)
    ) or 0


def count_users_for_tenant(session: Session, tenant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
    ) or 0
```

- [ ] **Step 3 : suite ciblée puis complète**

```bash
cd core && uv run pytest tests/test_quotas_service.py -v
cd core && uv run pytest
```

- [ ] **Step 4 : commit**

```bash
git add core/app/quotas/__init__.py core/app/quotas/service.py core/tests/test_quotas_service.py
git commit -m "feat(core): compteurs par tenant (items/collections/utilisateurs)"
```

---

## Task 2 : mesure de stockage — colonne `byte_size` sur les jobs de sortie

Prérequis pour mesurer les 2 buckets non tenant-préfixés (`exports`,
`appexports`, cf. spec §1.4) : aucune des deux tables n'a de colonne de
taille aujourd'hui — **vérifié**, pas à revérifier, mais la population de
cette colonne dans les jobs eux-mêmes doit être localisée précisément
avant d'écrire le correctif.

**Files:**
- Create: `core/alembic/versions/00XX_export_appexport_byte_size.py`
  (numéro exact à déterminer, Step 1)
- Modify: `core/app/export/models.py`, `core/app/appexport/models.py`
- Modify: `core/app/export/jobs.py`, `core/app/appexport/jobs.py`
- Create/Modify: `core/tests/test_export_jobs.py`,
  `core/tests/test_appexport_jobs.py` (noms exacts à vérifier avant de
  supposer — `ls core/tests | grep -i export`)

**Interfaces:**
- Consumes: `ExportJob.result_key`, `AppExportJob.result_key` (déjà
  présents) ; le client S3 déjà injecté dans ces jobs (`get_s3_client`-like
  dependency, patron déjà utilisé par les 6 autres modules qui écrivent du
  binaire).
- Produces: `ExportJob.byte_size`, `AppExportJob.byte_size` — consommés
  par la Tâche 3 (`job_output_storage_bytes`).

- [ ] **Step 1 : déterminer le prochain numéro de migration et le point
  exact de population**

```bash
ls core/alembic/versions | sort | tail -5
grep -n "result_key\s*=\|s3.*put_object\|s3.*upload" core/app/export/jobs.py core/app/appexport/jobs.py
```

Ne pas supposer où la taille est connue avant de lire ce grep — le fichier
qui uploade sait forcément la taille de ce qu'il vient d'écrire (soit un
buffer déjà en mémoire dont `len()` suffit, soit un `head_object` après
upload comme le fait déjà `attachments/routes.py:212-222`, cf. spec §1.5).

- [ ] **Step 2 : migration additive**

Colonnes `Integer, nullable=True` sur les deux tables — nullable parce que
les lignes historiques n'ont pas cette information (limitation assumée,
documentée dans la docstring de la migration, cf. spec §3.1). Tester
upgrade/downgrade/upgrade sur base non vide (piège CLAUDE.md n°8) : insérer
une ligne `ExportJob`/`AppExportJob` avant `upgrade`, vérifier qu'elle
survit avec `byte_size IS NULL`.

- [ ] **Step 3 : modèles SQLAlchemy**

```python
# core/app/export/models.py (et appexport/models.py, même patron)
byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 4 : population dans les jobs — test d'abord**

Écrire un test qui falsifie l'absence de population actuelle (le test
échoue avant le correctif : un job d'export/appexport terminé a
`byte_size is None`), puis coder la population au point trouvé au Step 1,
puis re-vérifier que le test passe.

- [ ] **Step 5 : suite complète + régénération OpenAPI (diff attendu vide
  — aucune route de réponse HTTP ne change de forme à cette tâche)**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

- [ ] **Step 6 : commit**

```bash
git add core/alembic/versions/*.py core/app/export/models.py core/app/appexport/models.py \
  core/app/export/jobs.py core/app/appexport/jobs.py core/tests/test_export_jobs.py \
  core/tests/test_appexport_jobs.py
git commit -m "feat(core): trace la taille des rendus d'export et bundles appexport"
```

---

## Task 3 : mesure de stockage complète + `GET /admin/usage`

**Files:**
- Modify: `core/app/quotas/service.py`
- Create: `core/app/quotas/routes.py`
- Create: `core/tests/test_quotas_routes.py`
- Modify: `core/app/main.py` (montage du routeur)

**Interfaces:**
- Consumes: Tâches 1+2 ; les 4 buckets tenant-préfixés (env vars déjà
  définies, `S3_UPLOADS_BUCKET`/`S3_ATTACHMENTS_BUCKET`/
  `S3_TILESET3D_BUCKET`/`S3_TERRAIN3D_BUCKET`) ; `Privilege.
  SETTINGS_INSTANCE_MANAGE` (`core/app/roles/privileges.py`).
- Produces: `UsageSnapshot` (Pydantic), consommé par la Tâche 5 (garde de
  quota) et par le shell (Tâche 5 aussi, panneau admin).

- [ ] **Step 1 : test du calcul de stockage S3 (avant l'implémentation)**

```python
# core/tests/test_quotas_service.py (extension)
def test_tenant_prefixed_storage_bytes_sums_only_this_tenant_prefix(s3_stub, ...):
    # poser 2 objets sous "tenant-a/...", 1 objet sous "tenant-b/...", tailles connues
    # assert tenant_prefixed_storage_bytes(s3_stub, bucket, "tenant-a") == somme attendue
```

Réutiliser le double S3 en mémoire déjà utilisé par les tests d'autres
modules (`core/tests/conftest.py` ou un stub local à
`test_attachments_routes.py` — localiser avant de réinventer, `grep -rn
"class.*S3\|MemoryS3\|moto" core/tests`).

- [ ] **Step 2 : implémenter `tenant_prefixed_storage_bytes` et
  `job_output_storage_bytes`, puis `usage_for_tenant`**

Pagination S3 explicite (`list_objects_v2` peut tronquer à 1000 clés,
suivre `IsTruncated`/`NextContinuationToken` — piège classique si oublié,
un tenant avec plus de 1000 objets sous-compterait silencieusement son
usage réel).

- [ ] **Step 3 : route `GET /admin/usage`**

```python
@router.get("/admin/usage", response_model=UsageSnapshot)
def get_usage(user: User = Depends(get_current_user), session=Depends(get_session), s3=Depends(get_s3_client)):
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    return usage_for_tenant(session, s3, user.tenant_id)
```

Vérifier au préalable le nom exact de la dépendance `get_s3_client`
utilisée par un module voisin (`core/app/attachments/routes.py` ou
`core/app/ingestion/routes.py`) plutôt que d'en supposer un.

- [ ] **Step 4 : test de la route (privilège requis, 403 sans lui, forme
  de la réponse)**

- [ ] **Step 5 : suite complète + régénération OpenAPI/types TS (diff
  NON vide attendu cette fois — nouvelle route)**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 6 : commit**

```bash
git add core/app/quotas/ core/app/main.py core/openapi.json shell/src/api/generated/core-schema.d.ts \
  core/tests/test_quotas_routes.py
git commit -m "feat(core): GET /admin/usage — mesure de stockage et de comptage par tenant"
```

---

## Task 4 : capacité `CORE_QUOTAS_ENABLED` + limites configurables

**Files:**
- Modify: `core/app/auth/dependency.py` (`is_quotas_enabled`)
- Modify: `core/app/auth/routes.py` (`MeCapabilities.quotasEnabled`)
- Modify: `core/app/instance/routes.py` (twin de `GET /me`)
- Modify: `core/tests/test_auth_me_capabilities.py` (étendre la parité)
- Modify: `core/app/quotas/service.py` (lecture des 3 limites env)
- Modify: `docker-compose.yml`, `.env.example`
- Modify: `core/tests/test_deployability.py` si une règle explicite le
  demande (à vérifier — la plupart des règles existantes sont génériques
  et n'ont pas besoin d'être éditées pour une nouvelle variable, seul le
  câblage réel dans `docker-compose.yml` compte pour elles)

**Interfaces:**
- Consumes: patron `is_etl_enabled`/`is_tileset3d_enabled`
  (`core/app/auth/dependency.py:41-72`), patron `MeCapabilities`
  (`core/app/auth/routes.py:30-47`).
- Produces: `is_quotas_enabled() -> bool`,
  `max_items_per_tenant() -> int | None`,
  `max_collections_per_tenant() -> int | None`,
  `max_storage_bytes_per_tenant() -> int | None` (None = pas de limite
  configurée, même quand la capacité est active — cf. Step 2).

- [ ] **Step 1 : test de parité étendu (avant le code)**

Étendre `core/tests/test_auth_me_capabilities.py` pour couvrir
`quotasEnabled` — le test doit échouer tant que seul un des deux endpoints
(`GET /me` ou `GET /instance`) porte le nouveau champ.

- [ ] **Step 2 : `is_quotas_enabled()` et lecteurs de limites**

```python
def is_quotas_enabled() -> bool:
    """CORE_QUOTAS_ENABLED — capacité instance-wide optionnelle, même
    convention que is_tileset3d_enabled : lue à chaque appel, sans cache.
    Défaut false : une instance qui monte en version n'applique aucune
    limite tant qu'elle n'a pas explicitement activé la capacité (design
    SP-58 §3.1)."""
    return os.environ.get("CORE_QUOTAS_ENABLED", "false").lower() == "true"


def max_items_per_tenant() -> int | None:
    raw = os.environ.get("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "")
    return int(raw) if raw else None
```

Même patron pour `max_collections_per_tenant`/`max_storage_bytes_per_
tenant`. Décision explicite (spec §3.1) : **une seule limite instance-wide,
appliquée à tout tenant identiquement** — pas de table de configuration
par tenant, cf. spec §2.2 (hors périmètre) pour le pourquoi.

- [ ] **Step 3 : câbler `MeCapabilities`/`GET /instance`, suite complète**

```bash
cd core && uv run pytest tests/test_auth_me_capabilities.py -v
cd core && uv run pytest
```

- [ ] **Step 4 : câblage réel (docker-compose.yml, .env.example,
  test_deployability.py)**

```bash
grep -n "CORE_TILESET3D_ENABLED" docker-compose.yml .env.example
```

Ajouter `CORE_QUOTAS_ENABLED`, `CORE_QUOTA_MAX_ITEMS_PER_TENANT`,
`CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT`,
`CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT` aux deux fichiers, sur le même
patron exact (commentaire, valeur par défaut commentée), puis :

```bash
cd core && uv run pytest tests/test_deployability.py -v
```

- [ ] **Step 5 : régénération OpenAPI/types TS (diff non vide — nouveau
  champ de réponse)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 6 : `shell/src/auth/capabilities.ts` — champ
  `InstanceCapabilities.quotasEnabled`**

Suivre le patron exact des 6 champs déjà présents (§1.6 de la spec) ; test
de non-régression sur `capabilities.test.ts` si un test paramétré existe
déjà sur la forme de `InstanceCapabilities` (vérifier avant de supposer).

- [ ] **Step 7 : commit**

```bash
git add core/app/auth core/app/instance core/app/quotas/service.py docker-compose.yml .env.example \
  core/tests/test_auth_me_capabilities.py shell/src/auth/capabilities.ts core/openapi.json \
  shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core,shell): capacité CORE_QUOTAS_ENABLED et limites instance-wide"
```

---

## Task 5 : application du quota aux points de création

**Files:**
- Modify: `core/app/configs/routes.py` (création d'item)
- Modify: `core/app/collections/routes.py` (création de collection)
- Modify: les 4 points de confirmation d'upload post-S3 (spec §1.5) :
  `core/app/attachments/routes.py` (`confirm_attachment`),
  `core/app/tileset3d/routes.py` (`complete_tileset3d_upload`),
  `core/app/terrain3d/routes.py` (route de confirmation, nom exact à
  vérifier), `core/app/ingestion/routes.py` (`create_upload_job`)
- Modify: `core/app/quotas/service.py` (`check_quota_or_raise` + erreur
  RFC 7807)
- Create/Modify: tests correspondants sur chacun des 6 sites

**Interfaces:**
- Consumes: Tâches 1-4 ; le générateur d'erreurs RFC 7807 déjà en place
  depuis SP-26 (`grep -rn "application/problem+json\|RFC ?7807"
  core/app` pour localiser le générateur exact avant d'écrire une
  nouvelle forme d'erreur).

- [ ] **Step 1 : localiser précisément les 6 points d'insertion réels**

```bash
grep -n "^def create_config\b" core/app/configs/routes.py
grep -n "^def create_collection\|^def.*collections/empty" core/app/collections/routes.py
```

Ne pas supposer les signatures — la spec (§3.1.2) le dit explicitement :
« à confirmer précisément par lecture du code au moment du plan ».

- [ ] **Step 2 : test de la garde de comptage (avant le code), pour
  `create_config`**

Créer `N` items jusqu'à la limite (via `CORE_QUOTA_MAX_ITEMS_PER_TENANT`
monkeypatché à une petite valeur), vérifier que le `N+1`-ième échoue avec
le code d'erreur attendu, et que **désactiver `CORE_QUOTAS_ENABLED`** fait
disparaître la garde (pas de régression sur le comportement par défaut,
capacité éteinte).

- [ ] **Step 3 : implémenter la garde sur `create_config`, rejouer le
  test, répéter Step 2+3 pour `create_collection`**

- [ ] **Step 4 : test de la garde de stockage (avant le code), sur
  `confirm_attachment`**

Poser un objet S3 dont la taille dépasserait le quota tenant restant,
vérifier le rejet **et** que l'objet S3 orphelin est nettoyé (même patron
que `MAX_ATTACHMENT_BYTES` déjà en place à la même fonction, spec §1.5) —
falsifier explicitement : retirer temporairement le nettoyage, confirmer
que le test s'en aperçoit (un objet resterait orphelin en S3), remettre.

- [ ] **Step 5 : implémenter la garde de stockage sur les 4 points de
  confirmation d'upload**

Chaque site appelle `check_quota_or_raise` avec la taille du fichier
qu'il vient de confirmer (déjà connue par tous les 4, cf. Tâche 2 Step 1
et spec §1.5) — pas de recalcul S3 complet à ce moment-là si la taille du
fichier confirmé suffit à la décision (usage actuel + cette taille vs
limite).

- [ ] **Step 6 : E2E — au moins un scénario qui vérifie le message
  d'erreur visible côté shell**

```bash
cd shell && npm run e2e -- --grep "quota"
```

(nom de spec à créer si aucun scénario équivalent n'existe déjà —
vérifier `ls shell/e2e | grep -i quota` avant de supposer qu'il faut en
créer un nouveau.)

- [ ] **Step 7 : suite complète des 3 suites**

```bash
cd core && uv run pytest
cd shell && npm run test && npm run e2e
```

- [ ] **Step 8 : commit**

```bash
git add core/app/configs/routes.py core/app/collections/routes.py core/app/attachments/routes.py \
  core/app/tileset3d/routes.py core/app/terrain3d/routes.py core/app/ingestion/routes.py \
  core/app/quotas/service.py core/tests shell/e2e
git commit -m "feat(core): applique les quotas d'items/collections/stockage aux points de création"
```

**Clôture du Volet A** : rejouer `uv run pytest` (cœur, complet),
`npm run test && npm run build && npm run e2e` (shell, complet), et
confirmer que GAP-73/GAP-11 sont couverts par la preuve de sortie du
chantier 4.22 (« un tenant qui dépasse son quota de stockage voit son
upload refusé avec un message clair ») avant d'attaquer le Volet B.

---

## Volet B — Droit à l'effacement

## Task 6 : migrations `users.erased_at` + table `purge_receipts`

**Files:**
- Create: `core/alembic/versions/00XX_erasure.py`
- Modify: `core/app/users/models.py` (`erased_at`)
- Create: `core/app/compliance/__init__.py`, `core/app/compliance/models.py`
  (`PurgeReceipt`)
- Create: `core/tests/test_compliance_models.py` (ou nom équivalent
  vérifié contre la convention du dépôt)

**Interfaces:**
- Consumes: aucune (tables/colonnes nouvelles, additives).
- Produces: `User.erased_at`, `PurgeReceipt` — consommés par les Tâches 7
  et 9.

- [ ] **Step 1 : localiser le prochain numéro de migration réel**

```bash
ls core/alembic/versions | sort | tail -5
```

- [ ] **Step 2 : écrire la migration**

`users.erased_at` : `DateTime, nullable=True`, additive.

`purge_receipts` : **volontairement sans `ForeignKey` vers `tenants`**
(spec §3.3 Step 8 — la ligne doit survivre à la suppression du tenant
qu'elle documente) :

```python
op.create_table(
    "purge_receipts",
    sa.Column("id", sa.String(), primary_key=True),
    sa.Column("tenant_slug", sa.String(), nullable=False),
    sa.Column("requested_by_user_id", sa.String(), nullable=False),
    sa.Column("requested_at", sa.DateTime(), nullable=False),
    sa.Column("completed_at", sa.DateTime(), nullable=True),
    sa.Column("counts", sa.JSON(), nullable=False),
)
```

- [ ] **Step 3 : modèle SQLAlchemy `PurgeReceipt`**

```python
# core/app/compliance/models.py
class PurgeReceipt(Base):
    __tablename__ = "purge_receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False)
```

Aucun champ ne doit contenir de donnée personnelle — commentaire de tête
explicite dans le fichier, sur le patron de `app/audit/models.py` (`actor_
id` sans FK, même rationale, spec §1.3/§3.3).

- [ ] **Step 4 : test de la migration sur base non vide (upgrade puis
  downgrade puis re-upgrade), piège CLAUDE.md n°8**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

```bash
git add core/alembic/versions/*.py core/app/users/models.py core/app/compliance/ core/tests
git commit -m "feat(core): schéma pour l'anonymisation utilisateur et la preuve de purge"
```

---

## Task 7 : anonymisation d'un utilisateur

**Files:**
- Create: `core/app/compliance/service.py` (`anonymize_user`)
- Create ou modifier: `core/app/users/routes.py` (**n'existe pas
  aujourd'hui**, vérifié §1.2 de la spec — créer le fichier) ou
  `core/app/compliance/routes.py` (à trancher, cf. spec §6 — cette tâche
  choisit `core/app/compliance/routes.py` pour garder les deux opérations
  de conformité au même endroit, en cohérence avec la Tâche 9 ; documenter
  ce choix dans le message de commit)
- Modify: `core/app/main.py` (montage du routeur)
- Create: `core/tests/test_compliance_service.py`,
  `core/tests/test_compliance_routes.py`

**Interfaces:**
- Consumes: `User` (`core/app/users/models.py`, contrainte
  `uq_users_tenant_oidc_sub`), `Notification`
  (`recipient_user_id`), `GroupMember` (`core/app/sharing/models.py`),
  `Privilege.ADMIN_USERS_MANAGE` (déjà existant, consommé par
  `UsersAdminPage`).
- Produces: `POST /compliance/users/{user_id}/erase`.

- [ ] **Step 1 : test caractéristique de ce que l'anonymisation doit
  préserver (avant le code)**

Créer un utilisateur avec : un item qu'il possède, une collection qu'il
possède, une pièce jointe qu'il a uploadée, une notification qui lui est
adressée, une appartenance à un groupe. Appeler `anonymize_user`.
Vérifier :
- `username`/`email`/`first_name`/`last_name` écrasés, `oidc_sub` changé
  et toujours unique (contrainte respectée — insérer un second appel sur
  un autre utilisateur du même tenant pour confirmer qu'aucune collision
  n'est possible).
- `erased_at` renseigné.
- L'item et la collection **existent toujours**, `owner_id` inchangé
  (pointent vers la ligne anonymisée).
- La pièce jointe existe toujours, `created_by` inchangé.
- La notification **a disparu**.
- L'appartenance au groupe **a disparu**.
- Un second appel sur le même `user_id` échoue explicitement (idempotence,
  pas de double écriture silencieuse).

- [ ] **Step 2 : falsifier ce test avant de l'accepter**

Retirer temporairement la suppression des notifications dans une version
brouillon de `anonymize_user`, confirmer que le test Step 1 s'en aperçoit
(échec sur l'assertion "notification a disparu"), remettre — preuve que
le test protège réellement ce qu'il prétend protéger (piège CLAUDE.md
n°10).

- [ ] **Step 3 : implémenter `anonymize_user`**

```python
# core/app/compliance/service.py
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.notifications.models import Notification
from app.sharing.models import GroupMember
from app.users.models import User


class UserAlreadyErasedError(Exception):
    pass


def anonymize_user(session: Session, *, tenant_id: str, user_id: str) -> None:
    user = session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise LookupError("user not found in this tenant")
    if user.erased_at is not None:
        raise UserAlreadyErasedError(user_id)
    user.username = f"utilisateur-efface-{user_id[:8]}"
    user.email = None
    user.first_name = ""
    user.last_name = ""
    user.oidc_sub = f"erased:{uuid.uuid4()}"
    user.erased_at = datetime.now(UTC)
    session.execute(delete(Notification).where(Notification.recipient_user_id == user_id))
    session.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
    session.flush()
```

Vérifier le nom exact du modèle `GroupMember`/ses colonnes avant de
copier ce squelette verbatim (`core/app/sharing/models.py:24-30`, déjà lu
pendant la recherche de cette spec, mais à reconfirmer si SP-43 ou une
autre session a renommé le module entre-temps).

- [ ] **Step 4 : routes**

`POST /compliance/users/{user_id}/erase` : si `user_id` est l'id de
l'appelant (ou le littéral `"me"`, à trancher), aucun privilège
supplémentaire ; sinon `require_privilege(session, user,
Privilege.ADMIN_USERS_MANAGE.value)`. Toujours vérifier que la cible
appartient au même tenant que l'appelant (jamais d'anonymisation
cross-tenant, même avec le privilège).

- [ ] **Step 5 : audit — jamais l'ancien username/email dans le payload**

```python
write_audit(session, tenant_id=..., actor_id=user.id, actor_kind="user",
            action="user.erase", object_type="user", object_id=user_id, payload={})
```

Test dédié qui vérifie que `payload` ne contient ni l'ancien username ni
l'ancien email (falsifier : les y mettre temporairement, confirmer que le
test casse, retirer).

- [ ] **Step 6 : suite complète + régénération OpenAPI/types TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 7 : commit**

```bash
git add core/app/compliance/ core/app/main.py core/openapi.json \
  shell/src/api/generated/core-schema.d.ts core/tests
git commit -m "feat(core): anonymisation d'un utilisateur (droit à l'effacement, RGPD Art. 17)"
```

---

## Task 8 : privilège dédié `compliance.manage`

Prérequis pour la Tâche 10 (purge de tenant) — livré comme tâche séparée
parce qu'il touche 3 surfaces indépendantes (enum Python, i18n shell,
éventuellement rôle prédéfini) qui méritent chacune leur propre commit et
vérification.

**Files:**
- Modify: `core/app/roles/privileges.py`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Modify (si décidé, cf. Step 3) : `core/app/roles/privileges.py`
  (`BUILT_IN_ROLE_PRIVILEGES`)
- Modify: `core/tests/test_roles_*.py` (nom exact à vérifier — la
  suite qui teste le catalogue de 18 privilèges doit être étendue à 19)

**Interfaces:**
- Consumes: aucune.
- Produces: `Privilege.COMPLIANCE_MANAGE`, consommé par la Tâche 10.

- [ ] **Step 1 : test qui échoue avant l'ajout (compte de privilèges)**

Si un test existant affirme littéralement « 18 privilèges »
(`core/tests/test_roles_*.py`, à localiser par `grep -rn "18" core/tests
--include=test_roles*"`), il doit être mis à jour vers 19 **dans le même
commit** que l'ajout — sinon la tâche casse un test existant plutôt que
d'en ajouter un.

- [ ] **Step 2 : ajouter la valeur d'enum + métadonnées**

```python
# core/app/roles/privileges.py
class Privilege(StrEnum):
    ...
    COMPLIANCE_MANAGE = "compliance.manage"

PRIVILEGE_METADATA: dict[Privilege, tuple[str, str]] = {
    ...
    Privilege.COMPLIANCE_MANAGE: ("settings", "roles.privilege.complianceManage"),
}
```

Domaine `"settings"` proposé par analogie avec `SETTINGS_INSTANCE_MANAGE`
(même famille shell, cf. `shell/src/auth/capabilities.ts`) — à confirmer
plutôt qu'à imposer si un domaine `"compliance"` dédié semble préférable
au moment de l'exécution (impacterait aussi `DomainId` côté shell, cf.
spec §6, décision non tranchée par la spec).

- [ ] **Step 3 : décision explicite — aucun rôle prédéfini ne porte ce
  privilège par défaut**

Ne **pas** l'ajouter à `BUILT_IN_ROLE_PRIVILEGES["administrateur"]` sans
décision consciente (spec §3.3) — laisser ce privilège **hors** des 4
rôles prédéfinis à l'issue de cette tâche ; un rôle sur mesure devra être
créé explicitement par un admin de tenant pour l'attribuer à qui de
droit. Ajouter un test qui affirme explicitement cette absence (« aucun
rôle prédéfini ne porte compliance.manage ») pour que ce choix ne dérive
pas silencieusement à une prochaine session.

- [ ] **Step 4 : `shell/src/i18n/catalog.fr.ts`**

```ts
"roles.privilege.complianceManage": "Purger toutes les données d'un tenant (RGPD, irréversible)",
```

Libellé volontairement explicite sur le caractère irréversible — cohérent
avec `RolesAdminPage` qui affiche ce libellé à côté de la case à cocher
d'attribution de rôle.

- [ ] **Step 5 : suite complète (cœur + shell)**

```bash
cd core && uv run pytest
cd shell && npm run test
```

- [ ] **Step 6 : commit**

```bash
git add core/app/roles/privileges.py core/tests shell/src/i18n/catalog.fr.ts
git commit -m "feat(core,shell): privilège dédié compliance.manage (purge de tenant)"
```

---

## Task 9 : `purge_tenant` — service de suppression complète, filet caractéristique

**La tâche la plus risquée du plan** (spec §5, premier risque cité).
Aucune ligne de production observable ne change pour un tenant qui n'est
pas purgé — mais une erreur d'ordre ici est le pire résultat possible du
plan entier (données perdues à moitié, ou tenant bloqué dans un état
incohérent).

**Files:**
- Create: `core/app/compliance/purge.py`
- Create: `core/tests/test_compliance_purge.py`

**Interfaces:**
- Consumes: tous les modèles qui portent `tenant_id` (énumérés
  dynamiquement, cf. Step 1 — **pas une liste recopiée à la main**, même
  piège que `toFrontLayer()` cité par la spec §5) ; `remove_table_from_
  publication` et la fonction de `DROP TABLE` déjà utilisées par
  `unregister_collection` (`core/app/collections/routes.py:577-624`,
  `repo.delete_collection`) ; `PurgeReceipt` (Tâche 6).
- Produces: `purge_tenant(session, s3, *, tenant_id, requested_by_user_id)
  -> PurgeReceipt` — consommé par la Tâche 10 (job procrastinate).

- [ ] **Step 1 : écrire le filet caractéristique AVANT tout code de
  purge**

```python
# core/tests/test_compliance_purge.py
"""Test caractéristique (patron spec SP-43 §1.2/§5, appliqué ici à la
purge de tenant) : énumère tous les modèles SQLAlchemy qui portent une
colonne tenant_id via Base.registry.mappers plutôt qu'une liste recopiée
à la main — un futur module qui ajoute tenant_id sans être couvert par
purge_tenant serait autrement invisible."""

from app.db import Base


def _models_with_tenant_id():
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "tenant_id"):
            yield cls


def test_purge_tenant_removes_every_row_in_every_tenant_scoped_table(session, s3, ...):
    tenant_id = _create_tenant_with_one_row_in_every_model(session, _models_with_tenant_id())
    purge_tenant(session, s3, tenant_id=tenant_id, requested_by_user_id="u1")
    for cls in _models_with_tenant_id():
        remaining = session.scalar(
            select(func.count()).select_from(cls).where(cls.tenant_id == tenant_id)
        )
        assert remaining == 0, f"{cls.__name__} still has rows for the purged tenant"
```

`_create_tenant_with_one_row_in_every_model` est la partie non triviale de
ce test : chaque modèle a des colonnes obligatoires différentes (FK vers
un item, une collection, un utilisateur…) — construire ces lignes dans le
bon ordre de dépendances (parent avant enfant, l'inverse de la purge) est
un vrai morceau de code de test, à écrire avec autant de soin que le code
de production qu'il protège. Prévoir qu'il faudra probablement une
factory par modèle plutôt qu'une fonction générique.

- [ ] **Step 2 : lancer le test, confirmer qu'il échoue partout (aucun
  code de purge n'existe encore)**

```bash
cd core && uv run pytest tests/test_compliance_purge.py -v
```

- [ ] **Step 3 : implémenter `purge_tenant`, table par table, dans
  l'ordre de la spec §3.3**

Après chaque table ajoutée à l'implémentation, relancer le test complet
(pas seulement s'arrêter à la première table qui passe) — le message
d'assertion nomme la classe encore en défaut, ce qui guide directement
l'ordre d'implémentation restant.

```python
# core/app/compliance/purge.py — squelette, ordre à respecter strictement
def purge_tenant(session, s3, *, tenant_id, requested_by_user_id):
    started_at = datetime.now(UTC)
    counts = {}
    # 1. items (config_revisions -> configs -> item_shares -> items)
    # 2. collections (retrait publication CDC -> DROP TABLE dynamique -> ligne collections)
    # 3. objets S3 des 4 buckets tenant-préfixés (list + delete_objects par lot)
    #    + objets des 2 buckets de sortie de job (itération par result_key)
    # 4. attachments, export_jobs, app_export_jobs, tileset3d_jobs, terrain3d_jobs,
    #    ingestion_jobs, notifications, notification_read, secrets, harvest_sources
    #    (+ tables filles), mapicons, extensions, group_members, groups
    # 5. users
    # 6. roles (après users, qui les référencent par role_id)
    # 7. audit_log
    receipt = PurgeReceipt(
        id=..., tenant_slug=..., requested_by_user_id=requested_by_user_id,
        requested_at=started_at, completed_at=datetime.now(UTC), counts=counts,
    )
    session.add(receipt)
    session.flush()
    # 8. (écrit avant l'étape 9 : le receipt doit exister avant que le tenant
    #    disparaisse, sinon aucune trace de son tenant_slug ne survivrait)
    # 9. tenant
    return receipt
```

Chaque étape incrémente `counts[table_name]` avec le nombre de lignes
supprimées — c'est ce dictionnaire qui finit dans `PurgeReceipt.counts`.

- [ ] **Step 4 : test explicite sur la pagination S3 (>1000 objets)**

Même piège que la Tâche 3 Step 2 : un tenant dont un bucket contient plus
de 1000 objets doit voir **tous** ses objets supprimés, pas seulement la
première page — falsifier en posant 1001 objets factices (ou en mockant
la pagination S3) et confirmer que le test échoue sans la boucle de
pagination, avant de l'ajouter.

- [ ] **Step 5 : test d'idempotence partielle (reprise après crash)**

Simuler un `purge_tenant` interrompu après l'étape 4 (lever une exception
injectée juste après la suppression des `users`, avant celle des
`roles`) puis rappeler `purge_tenant` sur le même tenant : la seconde
invocation ne doit pas planter sur des lignes déjà absentes (chaque
suppression doit être idempotente — `DELETE ... WHERE tenant_id = ...`
l'est par construction si aucune ligne ne subsiste, mais le `DROP TABLE`
d'une collection déjà droppée et le retrait d'une table déjà retirée de
la publication CDC doivent être vérifiés explicitement, pas supposés).

- [ ] **Step 6 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 7 : commit**

```bash
git add core/app/compliance/purge.py core/tests/test_compliance_purge.py
git commit -m "feat(core): purge_tenant — suppression complète et irréversible des données d'un tenant"
```

---

## Task 10 : route de purge, job asynchrone, confirmation, UI admin

**Files:**
- Modify: `core/app/compliance/routes.py` (route de déclenchement)
- Create: `core/app/compliance/jobs.py` (tâche procrastinate)
- Create: `core/tests/test_compliance_routes.py` (extension),
  `core/tests/test_compliance_jobs.py`
- Create (shell) : nouvelle page admin ou extension d'une page existante
  (nom exact à trancher — cf. spec §6 ; candidat : `shell/src/pages/
  ComplianceAdminPage.tsx`, dans le domaine `admin` déjà défini par
  `shell/src/auth/capabilities.ts`)
- Modify: `shell/src/api/itemClient.ts`/`hooks.ts` (ou leurs modules de
  domaine si SP-43 les a déjà scindés — vérifier `ls shell/src/api/
  domains/` avant de choisir où ajouter les nouvelles méthodes)
- Create: `shell/e2e/compliance-admin.spec.ts` (ou nom équivalent)

**Interfaces:**
- Consumes: Tâches 6-9 ; `Privilege.COMPLIANCE_MANAGE` (Tâche 8) ;
  `app.jobs.common` (session_factory/notify_best_effort, déjà extrait par
  SP-43 — `core/app/jobs/common.py`, vérifié présent pendant cette
  recherche).
- Produces: `POST /compliance/tenants/{tenant_id}/purge` (déclenche le
  job), `GET /compliance/purges/{purge_id}` (statut, patron `GET /uploads/
  {job_id}` déjà répété 4 fois dans ce dépôt).

- [ ] **Step 1 : test de la confirmation par slug (avant le code)**

```python
def test_purge_route_rejects_without_matching_slug_confirmation(...):
    resp = client.post(f"/compliance/tenants/{tenant_id}/purge", json={"confirmSlug": "mauvais-slug"})
    assert resp.status_code == 400
```

- [ ] **Step 2 : route de déclenchement**

```python
@router.post("/compliance/tenants/{tenant_id}/purge", status_code=202)
def request_tenant_purge(tenant_id: str, body: PurgeConfirmRequest, user=Depends(get_current_user), session=Depends(get_session)):
    require_privilege(session, user, Privilege.COMPLIANCE_MANAGE.value)
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant purge not supported")
    tenant = session.get(Tenant, tenant_id)
    if tenant is None or body.confirmSlug != tenant.slug:
        raise HTTPException(status_code=400, detail="confirmation slug mismatch")
    job_id = ...  # defer purge_tenant_task
    write_audit(session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
                action="tenant.purge_requested", object_type="tenant", object_id=tenant_id, payload={})
    return {"jobId": job_id}
```

Vérifier explicitement (test dédié) que `tenant_id != user.tenant_id`
est bien rejeté — rappel spec §1.2/§3.3 : aucun acteur cross-tenant
n'existe, cette route ne doit jamais permettre à un tenant d'en purger un
autre.

- [ ] **Step 3 : job procrastinate**

```python
# core/app/compliance/jobs.py
@app.task(queue="etl")
def purge_tenant_task(tenant_id: str, requested_by_user_id: str) -> None:
    factory = jobs_common.session_factory()
    with factory() as session:
        s3 = ...  # même client que le reste du module
        purge_tenant(session, s3, tenant_id=tenant_id, requested_by_user_id=requested_by_user_id)
        session.commit()
```

Vérifier le nom exact de la queue à utiliser (`"etl"` réutilisée par
analogie avec les autres jobs longs, ou une queue dédiée `"compliance"` —
décision à prendre en fonction de la politique de priorité déjà en place
pour `procrastinate`, à lire dans `core/app/worker/` ou équivalent avant
de trancher).

- [ ] **Step 4 : test du job (avec falsification du risque d'ordre)**

Réutiliser le test caractéristique de la Tâche 9 en le faisant passer par
le job plutôt que par un appel direct à `purge_tenant` — confirme que le
déclenchement asynchrone n'introduit pas de régression (session/commit
mal placés, par exemple).

- [ ] **Step 5 : suite complète + régénération OpenAPI/types TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 6 : UI shell — page/panneau admin**

Formulaire qui exige de retaper le slug du tenant avant d'activer le
bouton de purge (jamais une simple case à cocher, spec §3.3) ; affichage
distinct et non ambigu entre « anonymiser un utilisateur » (Tâche 7,
action limitée) et « purger tout le tenant » (cette tâche, irréversible)
— cf. risque §5 de la spec, ne pas les rapprocher visuellement.

- [ ] **Step 7 : E2E**

```bash
cd shell && npm run e2e -- --grep "compliance"
```

- [ ] **Step 8 : suite complète des 3 suites**

```bash
cd core && uv run pytest
cd shell && npm run test && npm run build && npm run e2e
```

- [ ] **Step 9 : commit**

```bash
git add core/app/compliance/ core/openapi.json shell/src/api shell/src/pages shell/e2e \
  shell/src/api/generated/core-schema.d.ts core/tests
git commit -m "feat(core,shell): purge de tenant asynchrone, confirmation par slug, UI admin"
```

---

## Clôture de plan

- [ ] **Suite complète finale** (les 3 suites, dans cet ordre, y compris
  les portes de qualité) :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
  && npm run e2e
uvx pre-commit run --all-files
```

- [ ] **Vérifier qu'aucun outil MCP n'expose ces fonctionnalités**
  (contrainte globale, décision explicite spec §2.2) :

```bash
grep -rn "quota\|anonymize_user\|purge_tenant" core/app/mcp
```

Attendu : vide. Si non vide, retirer avant de clore le plan.

- [ ] **Mettre à jour CLAUDE.md** (`### Livré`) avec une ligne SP-58
  résumant : compteurs et mesure de stockage par tenant (`GET /admin/
  usage`), capacité `CORE_QUOTAS_ENABLED` + garde aux points de création,
  anonymisation d'utilisateur (`POST /compliance/users/{id}/erase`),
  privilège `compliance.manage`, purge complète de tenant asynchrone avec
  confirmation par slug et `purge_receipts` comme preuve d'effacement. —
  **et rappeler explicitement dans cette même ligne** que la priorité
  relative de ce chantier reste conditionnée à Q2 (spec §0, §5 dernier
  risque) : livrer ce plan ne tranche pas cette question produit.
- [ ] **Documenter dans le suivi de clôture** toute décision prise parmi
  celles listées au §6 de la spec (privilège de `GET /admin/usage`,
  emplacement exact des routes/fichiers shell, valeurs par défaut des
  quotas, choix de calcul à la demande vs compteur incrémental) — ne pas
  les laisser implicites dans le code seul.
