# SP-17a — Worker d'export Playwright & `PrintLayout` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le socle d'export (A25) : un worker Playwright asynchrone qui rend la vraie page runtime du shell (carte ou app/dashboard) en PNG/PDF, une mise en page `printLayout` déclarative embarquée dans `MapConfig`/`AppConfig`, un bouton « Exporter » dans la visionneuse de carte et le runtime d'app/dashboard, le tout derrière une capacité instance-wide `CORE_EXPORT_ENABLED` (défaut désactivé).

**Architecture:** Nouveau module cœur `core/app/export/` (jobs procrastinate sur une file dédiée `export`, routes REST, modèle+repository) ; un jeton d'export éphémère (HS256, colocalisé dans `app.auth` pour respecter le contrat de couches) fait que le worker Playwright navigue la page runtime avec les mêmes droits que l'utilisateur qui a demandé l'export ; un nouveau conteneur `export-worker` (profil compose `export`, image dédiée avec Chromium) exécute le rendu, isolé du worker partagé pour ne pas alourdir son image. Côté shell : un `printLayout` optionnel round-trippé sur `MapConfig`/`AppConfig`, un mode `exportRender` qui affiche une page nue (sans chrome de builder) avec la mise en page imprimée, et un panneau de poll générique pour suivre le job.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy/procrastinate (cœur), Playwright Python (rendu headless), PyJWT (jeton d'export), boto3/MinIO (stockage + lien présigné), React/TypeScript/Vitest/Playwright (shell + E2E).

## Global Constraints

- **Design de référence :** `docs/superpowers/specs/2026-08-08-sp17a-worker-export-print-design.md`. Deux précisions mécaniques prises pendant ce plan, qui affinent (sans les contredire) le design : (1) le jeton d'export n'est **pas** à usage unique — sa révocation est uniquement le TTL court (~2 min), exactement comme les liens S3 présignés déjà utilisés partout dans ce dépôt (aucun précédent de jeton « consommable » n'existe dans le code) ; (2) le jeton ne porte **pas** de claim `item_id` — inutile : le worker connaît déjà l'item via la ligne `export_jobs` qu'il traite, et l'autorisation réelle vient des droits de l'utilisateur résolu, pas d'une comparaison d'item par requête.
- **Littéraux exacts, à utiliser mot pour mot dans toutes les tâches** (une divergence entre deux tâches — ex. `"succeeded"` dans l'une, `"done"` dans l'autre — est le bug de mismatch précisément documenté dans CLAUDE.md pour SP-16b) :
  - Statut de job : `"pending" | "running" | "done" | "error"`.
  - Format d'export : `"png" | "pdf"`.
  - `PrintLayout.pageSize` : `"a4" | "a3"`. `PrintLayout.orientation` : `"portrait" | "landscape"`.
  - Variables d'environnement nouvelles : `CORE_EXPORT_ENABLED` (bool string, défaut `false`), `CORE_EXPORT_TOKEN_SECRET` (chaîne, requise seulement quand un jeton est réellement minté/décodé), `SHELL_BASE_URL` (URL interne du service `shell`, seulement lue par `export-worker`).
  - Bucket S3 réutilisé tel quel : `S3_EXPORTS_BUCKET` (défaut `"geostudio-exports"`, déjà utilisé par `writer.export`, SP-15a) — pas de nouveau bucket.
- **Style cœur :** modules `app/export/*.py` commencent par `# SPDX-License-Identifier: Apache-2.0`. Champs Pydantic en camelCase direct (jamais de `Field(alias=...)` sauf cas déjà existant `Message.from_`). Accès : `items_repo.get_access_facts` + `can(session, user_id=..., action=..., item=facts)`, 404 (jamais 403) si `facts is None` ou lecture refusée — cf. `core/app/pipelines/routes.py::_require_pipeline_access`. Commit **avant** `defer_task(...)` partout (patron déjà établi, cf. `run_pipeline_route`).
- **Style shell :** un composant qui poll un job asynchrone n'utilise **pas** `useQuery`/`refetchInterval` — boucle récursive `async`/`setTimeout` manuelle via le client, cf. `shell/src/builder/pipeline/PipelineRunPanel.tsx`. Toute erreur de fetch est catchée explicitement et affichée en `role="alert"` — jamais avalée silencieusement (piège documenté CLAUDE.md/SP-16b).
- **Ne pas régresser :** les 13+ specs E2E existantes (`shell/e2e/`) et la suite `core/tests` restent vertes après chaque tâche.
- **Hors périmètre de ce plan** (cf. design, section « Hors périmètre ») : 3D, `ReportSchedule`, print CMJN pro, export de sites publics (`kind="site"`), légende cartographique riche (symbologie) — la légende d'export liste seulement les titres des couches visibles.

---

## File Structure

Cœur (nouveaux fichiers) :
- `core/app/export/__init__.py`
- `core/app/export/models.py` — table `export_jobs`.
- `core/app/export/repository.py` — CRUD `ExportJob`.
- `core/app/export/rendering.py` — fonction pure `render_export(page, format, print_layout) -> bytes`.
- `core/app/export/jobs.py` — tâche procrastinate `render_export_task`.
- `core/app/export/routes.py` — `POST /export`, `GET /export/jobs/{id}`.
- `core/app/auth/export_tokens.py` — jeton d'export (mint/decode), colocalisé dans `app.auth` pour respecter le contrat de couches (voir Tâche 4).
- `deploy/export-worker/Dockerfile`

Cœur (fichiers modifiés) :
- `core/app/configs/schemas.py` — `PrintLayout` + champ sur `BuilderConfig`.
- `core/app/auth/dependency.py` — `is_export_enabled()` + extension de `get_current_user`.
- `core/app/instance/routes.py` — `exportEnabled`.
- `core/app/ingestion/storage.py` — `generate_presigned_get_url`.
- `core/app/jobs.py` — `import_paths`.
- `core/app/main.py` — montage conditionnel du routeur export.
- `core/pyproject.toml` — dépendance `playwright`, contrat de couches import-linter.
- `.env.example`, `docker-compose.yml`.

Shell (nouveaux fichiers) :
- `shell/src/builder/print/PrintLayoutPanel.tsx` (+ `.test.tsx`)
- `shell/src/builder/print/ExportPanel.tsx` (+ `.test.tsx`)
- `shell/src/shell/exportReady.ts`
- `shell/src/shell/useIsExportRender.ts`
- `shell/e2e/export.spec.ts`

Shell (fichiers modifiés) :
- `shell/src/api/types.ts`, `shell/src/api/itemClient.ts`, `shell/src/api/hooks.ts`
- `shell/src/map/MapView.tsx`
- `shell/src/pages/MapEditorPage.tsx`, `shell/src/pages/AppBuilderPage.tsx`, `shell/src/pages/AppRuntimePage.tsx`
- `shell/src/auth/useAuth.ts`, `shell/src/auth/RequireAuth.tsx`, `shell/src/App.tsx`

---

### Task 1: `PrintLayout` — schéma cœur + régénération OpenAPI/TS

**Files:**
- Modify: `core/app/configs/schemas.py:313-334`
- Test: `core/tests/test_configs_schemas.py` (créer si absent, sinon ajouter)

**Interfaces:**
- Produces: `PrintLayout` (Pydantic, `core/app/configs/schemas.py`) — `pageSize: Literal["a4","a3"]="a4"`, `orientation: Literal["portrait","landscape"]="portrait"`, `title: str|None=None`, `showLegend: bool=True`, `showScaleBar: bool=True`, `showNorthArrow: bool=False`, `cartouche: str|None=None`. Champ `BuilderConfig.printLayout: PrintLayout | None = None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_configs_schemas.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig, PrintLayout


def test_print_layout_defaults():
    layout = PrintLayout()
    assert layout.pageSize == "a4"
    assert layout.orientation == "portrait"
    assert layout.showLegend is True
    assert layout.showScaleBar is True
    assert layout.showNorthArrow is False
    assert layout.title is None
    assert layout.cartouche is None


def test_print_layout_rejects_invalid_page_size():
    with pytest.raises(ValidationError):
        PrintLayout(pageSize="letter")


def test_builder_config_print_layout_optional_and_absent_by_default():
    config = BuilderConfig(
        kind="map",
        map={"basemap": {"style": "https://example.test/style.json"}, "view": {"center": [0.0, 0.0], "zoom": 3.0}},
    )
    assert config.printLayout is None


def test_builder_config_accepts_print_layout_on_map_kind():
    config = BuilderConfig(
        kind="map",
        map={"basemap": {"style": "https://example.test/style.json"}, "view": {"center": [0.0, 0.0], "zoom": 3.0}},
        printLayout={"pageSize": "a3", "orientation": "landscape", "title": "Carte des incidents"},
    )
    assert config.printLayout is not None
    assert config.printLayout.pageSize == "a3"
    assert config.printLayout.title == "Carte des incidents"


def test_builder_config_accepts_print_layout_on_app_kind():
    config = BuilderConfig(kind="app", layout={"type": "grid", "items": []}, printLayout={"cartouche": "GeoStudio"})
    assert config.printLayout is not None
    assert config.printLayout.cartouche == "GeoStudio"
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_configs_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'PrintLayout'`

- [ ] **Step 3: Implémenter**

Dans `core/app/configs/schemas.py`, insérer entre la fin de `AlertRulePayload` (ligne 313, juste après le `return self` du `_require_single_scalar_query`) et `class BuilderConfig(BaseModel):` (ligne 316) :

```python
class PrintLayout(BaseModel):
    pageSize: Literal["a4", "a3"] = "a4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    title: str | None = None
    showLegend: bool = True
    showScaleBar: bool = True
    showNorthArrow: bool = False
    cartouche: str | None = None
```

Puis, dans `class BuilderConfig`, ajouter le champ juste après `alert: AlertRulePayload | None = None` (ligne 334) :

```python
    printLayout: PrintLayout | None = None
```

Aucun changement à `_require_kind_payload` : `printLayout` est optionnel pour tous les kinds, sans validation croisée.

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_configs_schemas.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Régénérer l'OpenAPI + les types TS, vérifier l'absence de dérive**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Run: `cd core && git diff --stat openapi.json` puis `cd ../shell && git diff --stat src/api/generated/core-schema.d.ts`
Expected: les deux fichiers montrent un diff non vide contenant `PrintLayout`/`printLayout` (nouveau schéma ajouté) — pas d'erreur de génération.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_configs_schemas.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): SP-17a — schéma PrintLayout sur BuilderConfig"
```

---

### Task 2: Capacité `CORE_EXPORT_ENABLED` (cœur + shell)

**Files:**
- Modify: `core/app/auth/dependency.py:26-33`
- Modify: `core/app/instance/routes.py` (fichier complet)
- Test: `core/tests/test_export_enabled_flag.py` (nouveau)
- Modify: `shell/src/api/types.ts` (type `InstanceInfo`)
- Modify: `shell/src/api/hooks.ts` (`useInstanceInfo`)
- Test: `shell/src/api/hooks.test.ts` (ajouter un cas si le fichier existe, sinon créer)

**Interfaces:**
- Consumes: rien (nouvelle capacité indépendante).
- Produces: `is_export_enabled() -> bool` (`app.auth.dependency`). `GET /instance` renvoie désormais `{"readOnly": bool, "etlEnabled": bool, "exportEnabled": bool}`. `InstanceInfo` (shell) gagne `exportEnabled: boolean`.

- [ ] **Step 1: Écrire le test cœur qui échoue**

```python
# core/tests/test_export_enabled_flag.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_export_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_export_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_EXPORT_ENABLED", raising=False)
    assert is_export_enabled() is False


def test_is_export_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    assert is_export_enabled() is True
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    assert is_export_enabled() is False


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_reports_export_disabled_by_default(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": False, "exportEnabled": False}


def test_instance_reports_export_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["exportEnabled"] is True
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_export_enabled'`

- [ ] **Step 3: Implémenter côté cœur**

Dans `core/app/auth/dependency.py`, juste après `is_etl_enabled()` (après la ligne 32, avant `def admin_subs()`) :

```python
def is_export_enabled() -> bool:
    """CORE_EXPORT_ENABLED (SP-17a) — capacité instance-wide optionnelle,
    même convention que is_etl_enabled : lue à chaque appel, sans cache.
    Défaut false : le worker Playwright/export-worker n'est jamais requis
    pour faire tourner le reste de la plateforme."""
    return os.environ.get("CORE_EXPORT_ENABLED", "false").lower() == "true"
```

Remplacer le contenu de `core/app/instance/routes.py` par :

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_etl_enabled, is_export_enabled, is_read_only_mode

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
    }
```

- [ ] **Step 4: Vérifier que le test cœur passe**

Run: `cd core && uv run pytest tests/test_export_enabled_flag.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Écrire le test shell qui échoue**

Dans `shell/src/api/hooks.test.ts` (créer le fichier avec ce contenu s'il n'existe pas encore ; s'il existe, ajouter le test à la suite des tests existants) :

```typescript
import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ItemClientContext } from "./itemClientContext";
import { useInstanceInfo } from "./hooks";
import type { ItemClient } from "./itemClient";

function wrapper({ client }: { client: Partial<ItemClient> }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ItemClientContext.Provider value={client as ItemClient}>{children}</ItemClientContext.Provider>
    </QueryClientProvider>
  );
}

describe("useInstanceInfo", () => {
  it("exposes exportEnabled from the core", async () => {
    const client: Partial<ItemClient> = {
      getInstanceInfo: vi.fn().mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled: true }),
    };
    const { result } = renderHook(() => useInstanceInfo(), { wrapper: wrapper({ client }) });
    await waitFor(() => expect(result.current.data?.exportEnabled).toBe(true));
  });

  it("falls back to exportEnabled: false when the client mock doesn't implement getInstanceInfo", async () => {
    const { result } = renderHook(() => useInstanceInfo(), { wrapper: wrapper({ client: {} }) });
    await waitFor(() => expect(result.current.data).toEqual({ readOnly: false, etlEnabled: false, exportEnabled: false }));
  });
});
```

Note : vérifier le nom exact du module exportant le contexte React (`ItemClientContext`) en inspectant `shell/src/api/hooks.ts` (import déjà utilisé par `useItemClientInternal`) — utiliser le même import que les autres tests de hooks existants du même fichier de test s'il y en a déjà un, pour rester cohérent avec le harnais de test déjà en place dans ce dossier.

- [ ] **Step 6: Vérifier que le test shell échoue**

Run: `cd shell && npx vitest run src/api/hooks.test.ts`
Expected: FAIL — `exportEnabled` absent du type `InstanceInfo`/non renvoyé par le fallback.

- [ ] **Step 7: Implémenter côté shell**

Dans `shell/src/api/types.ts`, remplacer :

```typescript
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean };
```

par :

```typescript
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean };
```

Dans `shell/src/api/hooks.ts`, dans `useInstanceInfo`, remplacer le fallback :

```typescript
queryFn: () => client.getInstanceInfo?.() ?? Promise.resolve({ readOnly: false, etlEnabled: false }),
```

par :

```typescript
queryFn: () => client.getInstanceInfo?.() ?? Promise.resolve({ readOnly: false, etlEnabled: false, exportEnabled: false }),
```

- [ ] **Step 8: Vérifier que le test shell passe**

Run: `cd shell && npx vitest run src/api/hooks.test.ts`
Expected: PASS (2 tests, plus tous les tests existants du fichier)

- [ ] **Step 9: Documenter la variable d'environnement**

Dans `.env.example`, juste après la ligne `CORE_ETL_ENABLED=false` (ligne 58) :

```
CORE_EXPORT_ENABLED=false
```

- [ ] **Step 10: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py core/tests/test_export_enabled_flag.py shell/src/api/types.ts shell/src/api/hooks.ts shell/src/api/hooks.test.ts .env.example
git commit -m "feat: SP-17a — capacité CORE_EXPORT_ENABLED (cœur + shell)"
```

---

### Task 3: Table `export_jobs` + repository

**Files:**
- Create: `core/app/export/__init__.py` (vide)
- Create: `core/app/export/models.py`
- Create: `core/app/export/repository.py`
- Test: `core/tests/test_export_repository.py`

**Interfaces:**
- Produces: modèle SQLAlchemy `ExportJob` (table `export_jobs`) : `id: str` (PK, `uuid4().hex`), `tenant_id: str`, `item_id: str`, `user_id: str`, `format: str`, `status: str` (défaut `"pending"`), `error: str | None`, `result_key: str | None`, `created_at`, `started_at: datetime | None`, `finished_at: datetime | None`.
- Produces (repository) : `create_job(session, *, tenant_id, item_id, user_id, format) -> ExportJob`, `mark_running(session, *, job_id) -> None`, `mark_done(session, *, job_id, result_key) -> None`, `mark_error(session, *, job_id, error) -> None`, `get_job(session, *, tenant_id, job_id) -> ExportJob | None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_export_repository.py
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.tenants.repository import get_or_create_default_tenant


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_create_job_starts_pending():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    assert job.status == "pending"
    assert job.error is None
    assert job.result_key is None
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched is not None
    assert fetched.format == "png"


def test_mark_running_then_done():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="pdf")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_done(session, job_id=job.id, result_key="exports/item-1/x.pdf")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "done"
    assert fetched.result_key == "exports/item-1/x.pdf"
    assert fetched.started_at is not None
    assert fetched.finished_at is not None


def test_mark_error_never_leaves_status_running():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_error(session, job_id=job.id, error="render timeout")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert fetched.error == "render timeout"


def test_get_job_scoped_to_tenant():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id="item-1", user_id="user-1", format="png")
    session.commit()
    assert export_repo.get_job(session, tenant_id="other-tenant", job_id=job.id) is None
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export'`

- [ ] **Step 3: Implémenter**

`core/app/export/__init__.py` : fichier vide (juste le header ne s'applique pas à un `__init__.py` vide dans ce dépôt — vérifier `core/app/alerts/__init__.py` : s'il est vide, laisser `core/app/export/__init__.py` vide aussi, sans contenu).

```python
# core/app/export/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

```python
# core/app/export/repository.py
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.export.models import ExportJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(session: Session, *, tenant_id: str, item_id: str, user_id: str, format: str) -> ExportJob:
    job = ExportJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, item_id=item_id, user_id=user_id,
        format=format, status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> ExportJob | None:
    return session.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = _now()
    session.flush()


def mark_done(session: Session, *, job_id: str, result_key: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.result_key = result_key
    job.finished_at = _now()
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    job = session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error = error
    job.finished_at = _now()
    session.flush()
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_repository.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/export/__init__.py core/app/export/models.py core/app/export/repository.py core/tests/test_export_repository.py
git commit -m "feat(core): SP-17a — table export_jobs + repository"
```

---

### Task 4: Jeton d'export dans `app.auth` + extension de `get_current_user`

> **Placement délibéré** : le jeton d'export vit dans `app.auth`, pas dans `app.export`. Le contrat de couches import-linter place `app.auth` tout en bas (juste au-dessus de `app.audit`/`app.users`/`app.tenants`) — `app.export` sera ajouté bien plus haut (à côté de `app.pipelines`/`app.alerts`, Tâche 13). Si le jeton vivait dans `app.export`, `get_current_user` (dans `app.auth`) devrait l'importer — une violation de couche ascendante. En le mettant dans `app.auth`, c'est `app.export` (haut) qui importera `app.auth` (bas) pour *minter* un jeton, exactement comme `app.pipelines.jobs` importe déjà `app.auth.dependency.is_etl_enabled`.

**Files:**
- Create: `core/app/auth/export_tokens.py`
- Modify: `core/app/auth/dependency.py:59-108` (fonction `get_current_user`)
- Test: `core/tests/test_export_tokens.py`
- Test: `core/tests/test_auth_export_token.py`

**Interfaces:**
- Produces (`app.auth.export_tokens`) : `class ExportTokenError(Exception)`, `class ExportTokenClaims` (attributs `tenant_id: str`, `user_id: str`, `job_id: str`), `mint_export_token(*, tenant_id: str, user_id: str, job_id: str, ttl_seconds: int = 120) -> str`, `is_export_token(token: str) -> bool`, `decode_export_token(token: str) -> ExportTokenClaims` (lève `ExportTokenError`).
- Consumes (dans `dependency.py`) : les quatre symboles ci-dessus.

- [ ] **Step 1: Écrire le test du module de jeton, qui échoue**

```python
# core/tests/test_export_tokens.py
# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest

from app.auth.export_tokens import (
    ExportTokenError,
    decode_export_token,
    is_export_token,
    mint_export_token,
)


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")


def test_mint_and_decode_round_trip():
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    claims = decode_export_token(token)
    assert claims.tenant_id == "t1"
    assert claims.user_id == "u1"
    assert claims.job_id == "j1"


def test_is_export_token_true_for_export_token_false_for_rs256():
    export_token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    assert is_export_token(export_token) is True
    rs256_like = jwt.encode({"sub": "x"}, "irrelevant", algorithm="HS512")
    assert is_export_token(rs256_like) is False
    assert is_export_token("not-even-a-jwt") is False


def test_decode_rejects_expired_token(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1", ttl_seconds=-1)
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_tampered_signature(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "a-different-secret")
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_wrong_typ_claim():
    bad = jwt.encode({"typ": "not-export", "tenant_id": "t1", "user_id": "u1", "job_id": "j1",
                       "iat": int(time.time()), "exp": int(time.time()) + 60}, "test-export-secret", algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)


def test_decode_rejects_missing_claim():
    bad = jwt.encode({"typ": "export", "tenant_id": "t1"}, "test-export-secret", algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.export_tokens'`

- [ ] **Step 3: Implémenter le module de jeton**

```python
# core/app/auth/export_tokens.py
# SPDX-License-Identifier: Apache-2.0
"""Jeton d'export éphémère (SP-17a) : permet au worker Playwright de
naviguer la page runtime avec les droits réels de l'utilisateur qui a
demandé l'export, sans compte de service à droits larges. Révocation par
TTL court uniquement (~2 min) — pas de suivi « déjà consommé » : aucun
précédent de jeton à usage unique n'existe dans ce dépôt (les liens S3
présignés, seul mécanisme comparable, sont eux aussi révoqués par TTL
seul). Colocalisé dans app.auth (pas app.export) : voir la note de
placement dans le plan d'implémentation, tâche 4."""
import os
import time

import jwt

_ALGORITHM = "HS256"
_TYP = "export"
_REQUIRED_CLAIMS = ("tenant_id", "user_id", "job_id")


class ExportTokenError(Exception):
    pass


class ExportTokenClaims:
    def __init__(self, *, tenant_id: str, user_id: str, job_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.job_id = job_id


def _secret() -> str:
    return os.environ["CORE_EXPORT_TOKEN_SECRET"]


def mint_export_token(*, tenant_id: str, user_id: str, job_id: str, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    claims = {
        "typ": _TYP, "tenant_id": tenant_id, "user_id": user_id, "job_id": job_id,
        "iat": now, "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def is_export_token(token: str) -> bool:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return False
    return header.get("alg") == _ALGORITHM


def decode_export_token(token: str) -> ExportTokenClaims:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise ExportTokenError(str(exc)) from exc
    if claims.get("typ") != _TYP:
        raise ExportTokenError("wrong token type")
    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise ExportTokenError(f"missing claims: {missing}")
    return ExportTokenClaims(
        tenant_id=claims["tenant_id"], user_id=claims["user_id"], job_id=claims["job_id"],
    )
```

- [ ] **Step 4: Vérifier que le test du module de jeton passe**

Run: `cd core && uv run pytest tests/test_export_tokens.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Écrire le test de `get_current_user`, qui échoue**

```python
# core/tests/test_auth_export_token.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.auth.dependency import get_current_user
from app.auth.export_tokens import mint_export_token
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")
    monkeypatch.delenv("CORE_AUTH_MODE", raising=False)


def _session_with_user():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="Alice", last_name="", bootstrap_admin=False,
    )
    session.commit()
    return session, tenant, user


def test_get_current_user_accepts_valid_export_token():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id=user.id, job_id="job-1")
    resolved = get_current_user(authorization=f"Bearer {token}", session=session)
    assert resolved.id == user.id


def test_get_current_user_rejects_expired_export_token():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id=user.id, job_id="job-1", ttl_seconds=-1)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_export_token_for_wrong_tenant():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id="some-other-tenant", user_id=user.id, job_id="job-1")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_export_token_for_deleted_user():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id="never-existed", job_id="job-1")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_missing_bearer():
    session, _tenant, _user = _session_with_user()
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_falls_through_to_oidc_path_for_non_hs256_garbage(monkeypatch):
    # Un jeton qui n'est structurellement pas un jeton d'export (alg != HS256,
    # ou pas un JWT du tout) doit continuer vers le chemin OIDC existant, pas
    # planter — et échouer là avec le même 401/503 qu'avant cette tâche.
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example.test/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio")
    session, _tenant, _user = _session_with_user()
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer not-a-jwt-at-all", session=session)
    assert exc_info.value.status_code in (401, 503)
```

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_auth_export_token.py -v`
Expected: FAIL — jeton d'export non reconnu, `get_current_user` tente la validation RS256/JWKS et lève une erreur différente (probablement 503 réseau ou 401 générique sans passer par le chemin attendu) sur le premier test.

- [ ] **Step 7: Implémenter l'extension de `get_current_user`**

Dans `core/app/auth/dependency.py`, ajouter l'import en tête (après les imports existants, ligne 12) :

```python
from app.auth.export_tokens import ExportTokenError, decode_export_token, is_export_token
```

Puis, dans `get_current_user` (lignes 59-108), insérer le nouveau chemin juste après le bloc `if _mock_mode(): ...` (après la ligne 80, avant le `try:` du décodage RS256 ligne 82) :

```python
    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        user = session.get(User, claims.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid export token")
        return user
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_auth_export_token.py -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Vérifier l'absence de régression sur la suite auth existante**

Run: `cd core && uv run pytest tests/ -k auth -v`
Expected: PASS (tous les tests d'auth existants, notamment ceux qui exercent le mode mock et le chemin RS256/JWKS réel, restent verts)

- [ ] **Step 10: Documenter la variable d'environnement**

Dans `.env.example`, juste après `CORE_EXPORT_ENABLED=false` (ajouté Tâche 2) :

```
# Secret HMAC signant les jetons d'export éphémères (SP-17a) — chaîne
# quelconque, pas de format base64 requis (contrairement à
# CORE_SECRETS_MASTER_KEY). Lu paresseusement (os.environ[...], échec
# rapide) seulement quand un jeton est réellement minté/décodé — une
# instance qui n'active jamais CORE_EXPORT_ENABLED n'a pas besoin de le
# définir. Générer avec : openssl rand -base64 32
CORE_EXPORT_TOKEN_SECRET=
```

- [ ] **Step 11: Commit**

```bash
git add core/app/auth/export_tokens.py core/app/auth/dependency.py core/tests/test_export_tokens.py core/tests/test_auth_export_token.py .env.example
git commit -m "feat(core): SP-17a — jeton d'export HS256 + extension de get_current_user"
```

---

### Task 5: Presigned GET S3 + rendu pur (`app/export/rendering.py`)

**Files:**
- Modify: `core/app/ingestion/storage.py` (ajout d'une fonction)
- Create: `core/app/export/rendering.py`
- Test: `core/tests/test_ingestion_storage.py` (ajouter un cas si le fichier existe, sinon créer un fichier minimal ciblé)
- Test: `core/tests/test_export_rendering.py`

**Interfaces:**
- Produces: `generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str` (`app.ingestion.storage`). `class RenderPage(Protocol)` avec `screenshot(self, *, full_page: bool) -> bytes` et `pdf(self, *, format: str, landscape: bool) -> bytes`. `render_export(page: RenderPage, *, format: Literal["png","pdf"], print_layout: PrintLayout | None) -> bytes` (`app.export.rendering`).

- [ ] **Step 1: Écrire le test de presigned GET, qui échoue**

```python
# core/tests/test_ingestion_storage.py (ajouter à la suite si le fichier existe déjà)
from unittest.mock import MagicMock

from app.ingestion.storage import generate_presigned_get_url


def test_generate_presigned_get_url_calls_boto_with_get_object():
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://minio.example.test/bucket/key?sig=x"
    url = generate_presigned_get_url(client, bucket="geostudio-exports", key="renders/job-1.pdf", expires_in=1800)
    client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "geostudio-exports", "Key": "renders/job-1.pdf"}, ExpiresIn=1800,
    )
    assert url == "https://minio.example.test/bucket/key?sig=x"
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_presigned_get_url'`

- [ ] **Step 3: Implémenter `generate_presigned_get_url`**

Dans `core/app/ingestion/storage.py`, ajouter juste après `generate_presigned_put_url` (fin du fichier) :

```python
def generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in,
    )
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: PASS

- [ ] **Step 5: Écrire le test de `render_export`, qui échoue**

```python
# core/tests/test_export_rendering.py
# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import PrintLayout
from app.export.rendering import render_export


class _FakePage:
    def __init__(self):
        self.screenshot_calls = []
        self.pdf_calls = []

    def screenshot(self, *, full_page: bool) -> bytes:
        self.screenshot_calls.append(full_page)
        return b"PNGDATA"

    def pdf(self, *, format: str, landscape: bool) -> bytes:
        self.pdf_calls.append((format, landscape))
        return b"PDFDATA"


def test_render_export_png_takes_full_page_screenshot():
    page = _FakePage()
    result = render_export(page, format="png", print_layout=None)
    assert result == b"PNGDATA"
    assert page.screenshot_calls == [True]
    assert page.pdf_calls == []


def test_render_export_pdf_uses_default_layout_when_none():
    page = _FakePage()
    result = render_export(page, format="pdf", print_layout=None)
    assert result == b"PDFDATA"
    assert page.pdf_calls == [("A4", False)]


def test_render_export_pdf_respects_page_size_and_orientation():
    page = _FakePage()
    layout = PrintLayout(pageSize="a3", orientation="landscape")
    render_export(page, format="pdf", print_layout=layout)
    assert page.pdf_calls == [("A3", True)]
```

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.rendering'`

- [ ] **Step 7: Implémenter**

```python
# core/app/export/rendering.py
# SPDX-License-Identifier: Apache-2.0
"""Fonction de rendu pure (SP-17a) : ne connaît rien de Playwright, de S3 ni
de la navigation — prend une page déjà navigée/prête et produit des octets.
Testable avec un faux `page` (Protocol), le lancement du vrai navigateur
Chromium vit dans app.export.jobs (tâche 6), seul endroit qui a besoin d'un
Playwright réel installé."""
from typing import Literal, Protocol

from app.configs.schemas import PrintLayout


class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(self, *, format: str, landscape: bool) -> bytes: ...


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(format=layout.pageSize.upper(), landscape=layout.orientation == "landscape")
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add core/app/ingestion/storage.py core/app/export/rendering.py core/tests/test_ingestion_storage.py core/tests/test_export_rendering.py
git commit -m "feat(core): SP-17a — presigned GET S3 + rendu pur render_export"
```

---

### Task 6: Job procrastinate `render_export_task`

**Files:**
- Create: `core/app/export/jobs.py`
- Modify: `core/pyproject.toml` (dépendance `playwright`)
- Test: `core/tests/test_export_jobs.py`

**Interfaces:**
- Consumes: `export_repo.{get_job,mark_running,mark_done,mark_error}` (Tâche 3), `render_export` (Tâche 5), `mint_export_token` (Tâche 4), `configs_repo.get_config_by_item` (existant), `is_export_enabled` (Tâche 2).
- Produces: `render_export_task(job_id: str, tenant_id: str)` — tâche `@app.task(queue="export")`, jamais de job zombie (toute exception → `mark_error`). `_launch_and_navigate(url: str) -> RenderPage` — factorisée seule pour être monkeypatchable en test (seul point qui a besoin d'un vrai navigateur).

- [ ] **Step 1: Ajouter la dépendance Playwright**

Dans `core/pyproject.toml`, dans `dependencies = [...]`, ajouter après `"openpyxl>=3.1", ...` (avant les lignes `opentelemetry-*`) :

```toml
    "playwright>=1.45",  # SP-17a : rendu headless Chromium pour l'export
                        # PNG/PDF (app/export/jobs.py) — installé sans le
                        # binaire navigateur par défaut ; `playwright install
                        # --with-deps chromium` est requis en plus (fait dans
                        # le Dockerfile export-worker, tâche 13 ; à faire à la
                        # main en dev local pour lancer les tests marqués
                        # @pytest.mark.playwright de cette tâche).
```

Run : `cd core && uv sync`
Expected: `playwright` installé dans l'environnement (pas encore le binaire Chromium — normal, seul le test `@pytest.mark.playwright` en a besoin, guardé et skippable, cf. Step 6).

- [ ] **Step 2: Écrire le test qui échoue (orchestration, sans navigateur réel)**

```python
# core/tests/test_export_jobs.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.export import jobs as export_jobs
from app.export import repository as export_repo
from app.items.repository import create_item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def export_env(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")
    monkeypatch.setenv("SHELL_BASE_URL", "http://shell.test")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    db_path = tmp_path / "export_jobs.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="Alice", last_name="", bootstrap_admin=False,
    )
    item = create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="Carte test")
    configs_repo.create_config(
        session,
        BuilderConfig(kind="map", map={"basemap": {"style": "https://x.test/s.json"}, "view": {"center": [0.0, 0.0], "zoom": 2.0}}),
        item.id, tenant_id=tenant.id,
    )
    session.commit()
    return session, tenant, user, item


class _FakePage:
    def screenshot(self, *, full_page: bool) -> bytes:
        return b"PNGDATA"

    def pdf(self, *, format: str, landscape: bool) -> bytes:
        return b"PDFDATA"


def test_render_export_task_marks_done_on_success(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: _FakePage())
    uploaded = {}

    class _FakeS3Client:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            uploaded["bucket"] = Bucket
            uploaded["key"] = Key
            uploaded["body"] = Body

        def generate_presigned_url(self, *args, **kwargs):
            return "https://minio.test/presigned"

    monkeypatch.setattr(export_jobs, "_s3_client_from_env", lambda: _FakeS3Client())

    # Appel direct de la fonction tâche (pas .defer() + run_worker) : teste
    # l'orchestration synchrone, pas la file — pas besoin d'InMemoryConnector
    # ici (contrairement à core/tests/test_alert_jobs.py qui teste, lui, le
    # vrai chemin .defer()/run_worker).
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "done"
    assert refreshed.result_key is not None
    assert uploaded["bucket"] == "geostudio-exports"
    assert uploaded["body"] == b"PNGDATA"


def test_render_export_task_marks_error_when_export_disabled(db_session, monkeypatch):
    session, tenant, user, item = db_session
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"


def test_render_export_task_marks_error_never_zombie_on_navigation_failure(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()

    def _boom(url):
        raise RuntimeError("navigation timeout")

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", _boom)

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    refreshed = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert refreshed.status == "error"
    assert "navigation timeout" in refreshed.error


def test_render_export_task_missing_job_is_a_noop(db_session):
    session, tenant, _user, _item = db_session
    export_jobs.render_export_task(job_id="does-not-exist", tenant_id=tenant.id)  # ne doit pas lever
```

- [ ] **Step 3: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.jobs'`

- [ ] **Step 4: Implémenter**

```python
# core/app/export/jobs.py
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-17a) : rend une page runtime du shell en PNG/PDF
via Chromium headless. Tourne dans le conteneur export-worker dédié (queue
`export`, jamais le worker partagé — image trop lourde pour lui, cf. design
§Infrastructure). Toute erreur marque le job "error", jamais un job bloqué
en "running" (même critère qu'app.pipelines.jobs.run_pipeline_task)."""
import logging
import os

from app.auth.dependency import is_export_enabled
from app.auth.export_tokens import mint_export_token
from app.configs import repository as configs_repo
from app.db import make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export.rendering import RenderPage, render_export
from app.ingestion.storage import generate_presigned_get_url, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)

_CONTENT_TYPE = {"png": "image/png", "pdf": "application/pdf"}


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _launch_and_navigate(url: str) -> RenderPage:
    # Seule fonction de ce module qui a besoin d'un vrai Chromium — isolée
    # pour être monkeypatchée en test (cf. tests/test_export_jobs.py). Pas de
    # gestion de cycle de vie du navigateur ici au-delà de la navigation :
    # la tâche appelante ferme tout dans un `finally` (cf. render_export_task).
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_selector('[data-export-ready="true"]', timeout=30_000, state="attached")
    return page


@app.task(queue="export")
def render_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_export_enabled():
        with request_scoped_session(session_factory) as session:
            export_repo.mark_error(session, job_id=job_id, error="export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        export_repo.mark_running(session, job_id=job_id)
        item_id, user_id, export_format = job.item_id, job.user_id, job.format

    try:
        with request_scoped_session(session_factory) as session:
            config = configs_repo.get_config_by_item(session, item_id)
            if config is None:
                raise ValueError(f"export item '{item_id}' not found")
            print_layout = config.config.printLayout

        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        target_url = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}?exportToken={token}&exportRender=1"

        browser_page = _launch_and_navigate(target_url)
        try:
            content = render_export(browser_page, format=export_format, print_layout=print_layout)
        finally:
            browser_page.context.browser.close()

        result_key = f"renders/{job_id}.{export_format}"
        _s3_client_from_env().put_object(
            Bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
            Key=result_key, Body=content, ContentType=_CONTENT_TYPE[export_format],
        )
        with request_scoped_session(session_factory) as session:
            export_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            export_repo.mark_error(session, job_id=job_id, error=str(exc))
```

Note : `browser_page.context.browser.close()` suppose que `_launch_and_navigate` renvoie un vrai `playwright.sync_api.Page` en production (dont `.context.browser` existe) ; le `_FakePage` de test n'a pas cet attribut — c'est voulu, les tests d'orchestration (Step 2) ne passent jamais par ce chemin de fermeture puisqu'ils monkeypatchent `_launch_and_navigate` pour renvoyer un objet minimal AVANT le `try/finally` de fermeture. Si un test échoue sur `AttributeError` à la fermeture, adapter `_FakePage` pour exposer un `context.browser.close()` factice plutôt que de retirer l'appel réel.

- [ ] **Step 5: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Test guardé avec un vrai navigateur (best-effort, non bloquant)**

```python
# core/tests/test_export_jobs.py (ajouter à la suite)
import http.server
import socket
import threading

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.playwright
def test_launch_and_navigate_real_chromium_waits_for_export_ready(tmp_path):
    pytest.importorskip("playwright")
    (tmp_path / "index.html").write_text(
        '<html><body><script>setTimeout(() => { document.body.dataset.exportReady = "true"; }, 200);</script></body></html>'
    )
    port = _free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from app.export.jobs import _launch_and_navigate

        page = _launch_and_navigate(f"http://127.0.0.1:{port}/index.html")
        try:
            assert page.screenshot(full_page=True)
        finally:
            page.context.browser.close()
    finally:
        server.shutdown()
```

Run : `cd core && uv run playwright install --with-deps chromium && uv run pytest tests/test_export_jobs.py -v -m playwright`
Expected : PASS si Chromium peut s'installer dans cet environnement — **sinon SKIP proprement** (marqueur `@pytest.mark.playwright`, à enregistrer dans `core/pyproject.toml` `[tool.pytest.ini_options] markers` s'il existe une section de ce type, sinon dans `core/pytest.ini`/`conftest.py`). Si `playwright install` échoue faute de `sudo`/accès réseau dans cet environnement (risque déjà rencontré pour le sidecar QGIS, SP-15d), **documenter cet état exact dans le rapport de tâche** plutôt que de prétendre qu'il a tourné — ce test guardé n'est pas bloquant pour la suite du plan, toute la logique d'orchestration (Step 2) est déjà vérifiée sans navigateur réel.

- [ ] **Step 7: Commit**

```bash
git add core/app/export/jobs.py core/pyproject.toml core/tests/test_export_jobs.py core/uv.lock
git commit -m "feat(core): SP-17a — tâche procrastinate render_export_task"
```

---

### Task 7: Routes REST `POST /export` + `GET /export/jobs/{id}`

> **Ne pas oublier le garde démo** : `core/app/main.py:67-81` porte un middleware global `read_only_guard` qui bloque tout `POST`/`PUT`/`PATCH`/`DELETE` en `CORE_READ_ONLY_MODE=true`, sauf chemins déjà exemptés via `_EXPORT_PATH_RE` (ligne 38, qui ne couvre que les exports SP-16a `/collections/{id}/export`/`/datasets/{id}/arcgis/export`). `POST /export` (cette tâche) doit être ajouté à cette exemption — le design dit explicitement que l'export est une action de lecture, « même raisonnement que SP-16a » ; sans cet ajout, l'export serait silencieusement bloqué en 403 dès qu'une instance active le mode démo, alors même que rien dans les tests des tâches précédentes ne l'aurait détecté (ils ne passent jamais par `create_app()` avec `CORE_READ_ONLY_MODE=true`).

**Files:**
- Create: `core/app/export/routes.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_export_routes.py`

**Interfaces:**
- Consumes: `export_repo.*` (Tâche 3), `render_export_task` (Tâche 6), `is_export_enabled` (Tâche 2), `items_repo.get_access_facts`/`can` (existants).
- Produces: `POST /export` body `{"itemId": str, "format": "png"|"pdf"}` → 202 `{"jobId": str}`. `GET /export/jobs/{job_id}` → 200 `{"id": str, "status": str, "resultUrl": str|None, "error": str|None}`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_export_routes.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export import routes as export_routes
from app.items.repository import create_item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _fake_deferrer():
    # Même patron que core/tests/test_pipeline_routes.py::test_run_route_defers_job_and_returns_run_id
    # (client.app.dependency_overrides[routes.get_task_deferrer] = ...) — sans
    # cet override, POST /export appellerait le vrai render_export_task.defer(...)
    # contre le connecteur procrastinate réel (DATABASE_URL non défini dans ces
    # tests sqlite), et échouerait pour une raison sans rapport avec ce qui est testé.
    calls = []

    def deferrer(job_id, tenant_id):
        calls.append((job_id, tenant_id))

    return deferrer, calls


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        stranger = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        item = create_item(s, tenant_id=tenant.id, owner_id=owner.id, resource_type="map", title="Carte")
        configs_repo.create_config(
            s,
            BuilderConfig(kind="map", map={"basemap": {"style": "https://x.test/s.json"}, "view": {"center": [0.0, 0.0], "zoom": 2.0}}),
            item.id, tenant_id=tenant.id,
        )
        s.commit()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    def make_client():
        app = create_app()
        app.dependency_overrides[db.get_session] = override_session
        deferrer, calls = _fake_deferrer()
        app.dependency_overrides[export_routes.get_task_deferrer] = lambda: deferrer
        return TestClient(app), calls

    return make_client, owner, stranger, item.id


def test_post_export_requires_flag_enabled(env, monkeypatch):
    make_client, _owner, _stranger, item_id = env
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    client, _calls = make_client()  # le flag est lu à la construction (patron pipelines) : re-créer l'app
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404  # routeur jamais monté quand le flag est off


def test_post_export_creates_job_and_returns_202(env):
    make_client, owner, _stranger, item_id = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202
    assert "jobId" in response.json()
    assert len(calls) == 1


def test_post_export_denies_user_without_read_access(env):
    make_client, _owner, stranger, item_id = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    client.app.dependency_overrides[get_current_user_optional] = lambda: stranger
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404


def test_get_export_job_reports_status(env):
    make_client, owner, _stranger, item_id = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/export", json={"itemId": item_id, "format": "png"}).json()
    response = client.get(f"/export/jobs/{created['jobId']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["jobId"]
    assert body["status"] == "pending"
    assert body["resultUrl"] is None
    assert body["error"] is None


def test_get_export_job_unknown_id_is_404(env):
    make_client, owner, _stranger, _item_id = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.get("/export/jobs/does-not-exist")
    assert response.status_code == 404


def test_post_export_allowed_in_read_only_demo_mode(env, monkeypatch):
    # Garde démo (core/app/main.py::read_only_guard) : l'export est une
    # action de lecture (aucune écriture de donnée métier), doit rester
    # utilisable en CORE_READ_ONLY_MODE=true — même raisonnement que les
    # routes d'export SP-16a, déjà exemptées via _EXPORT_PATH_RE.
    make_client, owner, _stranger, item_id = env
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.routes'`

- [ ] **Step 3: Implémenter les routes**

```python
# core/app/export/routes.py
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'export (SP-17a) — montées uniquement quand
CORE_EXPORT_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête — même patron que app.pipelines.routes)."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task
from app.ingestion.storage import generate_presigned_get_url, make_s3_client
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

import os

router = APIRouter()


class CreateExportRequest(BaseModel):
    itemId: str
    format: str


class CreateExportResponse(BaseModel):
    jobId: str


class ExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None


def _require_export_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        render_export_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/export", response_model=CreateExportResponse, status_code=202)
def create_export_route(
    body: CreateExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> CreateExportResponse:
    if body.format not in ("png", "pdf"):
        raise HTTPException(status_code=422, detail="format must be 'png' or 'pdf'")
    _require_export_read_access(session, user=user, item_id=body.itemId)
    job = export_repo.create_job(session, tenant_id=user.tenant_id, item_id=body.itemId, user_id=user.id, format=body.format)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="export.create", object_type="export_job", object_id=job.id,
        payload={"itemId": body.itemId, "format": body.format},
    )
    # Commit avant de déférer : même raison que run_pipeline_route.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return CreateExportResponse(jobId=job.id)


@router.get("/export/jobs/{job_id}", response_model=ExportJobStatus)
def get_export_job_route(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExportJobStatus:
    job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="export job not found")
    _require_export_read_access(session, user=user, item_id=job.item_id)
    result_url = None
    if job.status == "done" and job.result_key:
        client = make_s3_client(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
        )
        result_url = generate_presigned_get_url(
            client, bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"), key=job.result_key,
        )
    return ExportJobStatus(id=job.id, status=job.status, resultUrl=result_url, error=job.error)
```

Dans `core/app/main.py`, ajouter l'import (à côté des autres imports de routes, en tête de fichier) :

```python
from app.auth.dependency import is_export_enabled
from app.export import routes as export_routes
```

Et, juste après le bloc `if is_etl_enabled(): app.include_router(pipelines_routes.router)` (ligne 105-106) :

```python
    if is_export_enabled():
        app.include_router(export_routes.router)
```

Enfin, exempter `POST /export` du garde lecture-seule démo (sinon 403 systématique dès `CORE_READ_ONLY_MODE=true`, cf. note en tête de cette tâche). Remplacer, ligne 38 :

```python
_EXPORT_PATH_RE = re.compile(r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$")
```

par :

```python
_EXPORT_PATH_RE = re.compile(r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$|^/export$")
```

(`GET /export/jobs/{id}` n'a pas besoin d'exemption : le middleware ne filtre que `POST`/`PUT`/`PATCH`/`DELETE`.)

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_routes.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Suite complète cœur**

Run: `cd core && uv run pytest tests/ -x -q`
Expected: PASS (aucune régression)

- [ ] **Step 6: Commit**

```bash
git add core/app/export/routes.py core/app/main.py core/tests/test_export_routes.py
git commit -m "feat(core): SP-17a — routes REST POST /export + GET /export/jobs/{id}"
```

---

### Task 8: Shell — types + itemClient (printLayout round-trip, ExportJob)

> **Point critique** : `PUT /configs/by-item/{pk}` remplace le document entier (pas de fusion partielle côté cœur — chaque révision est un snapshot complet, nécessaire au rollback versionné, SP-0). `saveMapConfig`/`saveAppConfig` construisent déjà leur corps de requête en énumérant explicitement chaque champ (jamais un spread `...config`) — omettre `printLayout` dans cette énumération ferait perdre silencieusement toute mise en page déjà enregistrée dès la prochaine sauvegarde d'un layer ou d'un widget, sans aucune erreur visible. Ce risque est réel dans ce dépôt (cf. CLAUDE.md, bugs de champ manquant/asymétrie lecture-écriture trouvés en revue SP-16a/SP-16b) — chaque test ci-dessous vérifie explicitement ce round-trip.

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts:590-606,760-832`
- Test: `shell/src/api/itemClient.test.ts` (ajouter aux tests existants du fichier)

**Interfaces:**
- Produces: `PrintLayoutConfig` (type TS), `MapConfig.printLayout?: PrintLayoutConfig | null`, `AppConfig.printLayout?: PrintLayoutConfig | null`, `ExportFormat = "png" | "pdf"`, `ExportJobStatus = "pending" | "running" | "done" | "error"`, `ExportJob = { id: string; status: ExportJobStatus; resultUrl: string | null; error: string | null }`. `itemClient.createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }>`, `itemClient.getExportJob(jobId: string): Promise<ExportJob>`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `shell/src/api/itemClient.test.ts` (mirror des tests existants du même fichier pour le style exact des mocks `fetch`/`request` — s'inspirer du test déjà présent pour `saveMapConfig`/`saveAppConfig` s'il y en a un, sinon suivre le style des tests `exportDataSource`) :

```typescript
describe("printLayout round-trip", () => {
  it("getMapConfig reads printLayout from the top level of the config, not nested under map", async () => {
    mockFetchOnce({
      config: {
        map: { basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [] },
        printLayout: { pageSize: "a3", orientation: "landscape", showLegend: true, showScaleBar: true, showNorthArrow: false },
      },
    });
    const config = await client.getMapConfig("pk-1");
    expect(config.printLayout).toEqual({ pageSize: "a3", orientation: "landscape", showLegend: true, showScaleBar: true, showNorthArrow: false });
  });

  it("saveMapConfig sends printLayout back at the top level, sibling of map", async () => {
    const fetchSpy = mockFetchOnce({});
    await client.saveMapConfig("pk-1", {
      basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [],
      printLayout: { pageSize: "a4", orientation: "portrait", showLegend: false, showScaleBar: false, showNorthArrow: false },
    });
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.printLayout).toEqual({ pageSize: "a4", orientation: "portrait", showLegend: false, showScaleBar: false, showNorthArrow: false });
    expect(body.map).toBeDefined();
  });

  it("getAppConfig reads printLayout", async () => {
    mockFetchOnce({ config: { kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", items: [] }, printLayout: { pageSize: "a4", orientation: "portrait", title: "Rapport" } } });
    const config = await client.getAppConfig("pk-2");
    expect(config.printLayout).toEqual({ pageSize: "a4", orientation: "portrait", title: "Rapport" });
  });

  it("saveAppConfig round-trips printLayout without dropping it", async () => {
    const fetchSpy = mockFetchOnce({});
    await client.saveAppConfig("pk-2", {
      kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", items: [] },
      printLayout: { pageSize: "a3", orientation: "landscape" },
    });
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
  });
});

describe("createExport / getExportJob", () => {
  it("createExport POSTs itemId and format", async () => {
    const fetchSpy = mockFetchOnce({ jobId: "job-1" });
    const result = await client.createExport("pk-1", "pdf");
    expect(result).toEqual({ jobId: "job-1" });
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain("/export");
    expect(JSON.parse(init.body)).toEqual({ itemId: "pk-1", format: "pdf" });
  });

  it("getExportJob GETs the job status by id", async () => {
    mockFetchOnce({ id: "job-1", status: "done", resultUrl: "https://minio.test/x.pdf", error: null });
    const job = await client.getExportJob("job-1");
    expect(job).toEqual({ id: "job-1", status: "done", resultUrl: "https://minio.test/x.pdf", error: null });
  });
});
```

Adapter `mockFetchOnce`/le nom exact du helper de mock `fetch` à celui déjà utilisé dans le reste de `shell/src/api/itemClient.test.ts` — inspecter le fichier avant d'écrire ces tests pour réutiliser le harnais existant tel quel (nom de la fonction de mock, forme de `client`, base URL).

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `printLayout` absent des types/du round-trip, `createExport`/`getExportJob` n'existent pas.

- [ ] **Step 3: Implémenter les types**

Dans `shell/src/api/types.ts`, ajouter avant `export type MapConfig = ...` (ligne 64) :

```typescript
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  showScaleBar?: boolean;
  showNorthArrow?: boolean;
  cartouche?: string | null;
};
```

Remplacer :

```typescript
export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[] };
```

par :

```typescript
export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[]; printLayout?: PrintLayoutConfig | null };
```

Dans `AppConfig` (ligne 414), ajouter le champ à la fin :

```typescript
export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
  navigationMode?: "tabs" | "story";
  interactions?: "auto" | "manual"; // absent = "manual"
  printLayout?: PrintLayoutConfig | null;
};
```

Ajouter, n'importe où dans le fichier près des autres types de statut (ex. à côté de `PipelineRunStatus`) :

```typescript
export type ExportFormat = "png" | "pdf";
export type ExportJobStatus = "pending" | "running" | "done" | "error";
export type ExportJob = { id: string; status: ExportJobStatus; resultUrl: string | null; error: string | null };
```

- [ ] **Step 4: Implémenter le round-trip dans `itemClient.ts`**

Remplacer `getMapConfig` (lignes 590-602) :

```typescript
    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map,
      // printLayout is a sibling top-level field (core/app/configs/schemas.py::BuilderConfig).
      const data = await request<{
        config?: {
          map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null;
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
        printLayout: data.config?.printLayout ?? null,
      };
    },
```

Remplacer `saveMapConfig` (ligne 604-606) :

```typescript
    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1, kind: "map",
        map: { basemap: config.basemap, view: config.view, layers: config.layers },
        printLayout: config.printLayout ?? null,
      });
    },
```

Remplacer `getAppConfig` (lignes 760-788), en ajoutant `printLayout` au type inline et au retour :

```typescript
    async getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig> {
      const qs = mode ? `?mode=${mode}` : "";
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
          navigationMode?: "tabs" | "story";
          interactions?: "auto" | "manual";
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}${qs}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
        navigationMode: c.navigationMode,
        interactions: c.interactions,
        printLayout: c.printLayout ?? null,
      };
    },
```

Remplacer `saveAppConfig` (lignes 819-832) :

```typescript
    async saveAppConfig(pk: string, config: AppConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: config.kind,
        theme: config.theme,
        dataSources: config.dataSources,
        messages: config.messages,
        pages: config.pages,
        variables: config.variables,
        layout: config.layout,
        navigationMode: config.navigationMode,
        interactions: config.interactions,
        printLayout: config.printLayout ?? null,
      });
    },
```

Ajouter les deux nouvelles méthodes, à la suite (n'importe où dans l'objet client, par exemple juste après `saveAppConfig`) :

```typescript
    async createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }> {
      return request<{ jobId: string }>("POST", `/export`, { itemId, format });
    },

    async getExportJob(jobId: string): Promise<ExportJob> {
      return request<ExportJob>("GET", `/export/jobs/${jobId}`);
    },
```

Ajouter les imports de type nécessaires en tête de fichier (`PrintLayoutConfig`, `ExportFormat`, `ExportJob`) à côté des autres imports depuis `"./types"`.

- [ ] **Step 5: Vérifier que les tests passent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: `npm run build` (vérification de types stricte)**

Run: `cd shell && npm run build`
Expected: succès — `tsc --noEmit` ne remonte aucune erreur de type sur les fichiers modifiés.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): SP-17a — round-trip printLayout + createExport/getExportJob"
```

---

### Task 9: `PrintLayoutPanel` + intégration dans les builders

**Files:**
- Create: `shell/src/builder/print/PrintLayoutPanel.tsx`
- Create: `shell/src/builder/print/PrintLayoutPanel.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`

**Interfaces:**
- Produces: `PrintLayoutPanel({ value, onChange }: { value: PrintLayoutConfig | null; onChange: (next: PrintLayoutConfig | null) => void })` — mêmes conventions de props que `PipelineScheduleEditor` (Tâche 9 du plan SP-15h).

- [ ] **Step 1: Écrire le test qui échoue**

```typescript
// shell/src/builder/print/PrintLayoutPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrintLayoutPanel } from "./PrintLayoutPanel";

describe("PrintLayoutPanel", () => {
  it("renders defaults when value is null", () => {
    render(<PrintLayoutPanel value={null} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Format")).toHaveValue("a4");
    expect(screen.getByLabelText("Orientation")).toHaveValue("portrait");
  });

  it("calls onChange with an updated title, preserving other fields", () => {
    // fireEvent.change (une seule valeur complète), pas userEvent.type
    // (frappe caractère par caractère) : le composant est entièrement
    // contrôlé et `onChange` ici est un mock qui ne réinjecte jamais la
    // nouvelle valeur dans `value` — avec userEvent.type, React réafficherait
    // `value=""` entre chaque frappe (le prop ne change jamais), et seul le
    // DERNIER caractère tapé survivrait dans le dernier appel à onChange.
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ pageSize: "a3", orientation: "landscape", showLegend: false }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Titre"), { target: { value: "Rapport" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3", orientation: "landscape", showLegend: false, title: "Rapport" }));
  });

  it("toggles showLegend", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ showLegend: true }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("Légende"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ showLegend: false }));
  });

  it("changing page size to a3 landscape calls onChange with both fields", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={null} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Format"), "a3");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3" }));
  });
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/builder/print/PrintLayoutPanel.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Implémenter**

```tsx
// shell/src/builder/print/PrintLayoutPanel.tsx
import type { PrintLayoutConfig } from "../../api/types";

const DEFAULTS: Required<Pick<PrintLayoutConfig, "pageSize" | "orientation" | "showLegend" | "showScaleBar" | "showNorthArrow">> = {
  pageSize: "a4", orientation: "portrait", showLegend: true, showScaleBar: true, showNorthArrow: false,
};

export function PrintLayoutPanel({
  value, onChange,
}: {
  value: PrintLayoutConfig | null;
  onChange: (next: PrintLayoutConfig | null) => void;
}) {
  const current = { ...DEFAULTS, ...(value ?? {}) };

  function patch(partial: Partial<PrintLayoutConfig>) {
    onChange({ ...current, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Mise en page d'impression</p>
      <label className="flex flex-col gap-1 text-sm">
        Format
        <select
          value={current.pageSize}
          onChange={(e) => patch({ pageSize: e.target.value as PrintLayoutConfig["pageSize"] })}
        >
          <option value="a4">A4</option>
          <option value="a3">A3</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Orientation
        <select
          value={current.orientation}
          onChange={(e) => patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })}
        >
          <option value="portrait">Portrait</option>
          <option value="landscape">Paysage</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <input type="text" value={current.title ?? ""} onChange={(e) => patch({ title: e.target.value || null })} />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showLegend} onChange={(e) => patch({ showLegend: e.target.checked })} />
        Légende
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showScaleBar} onChange={(e) => patch({ showScaleBar: e.target.checked })} />
        Barre d'échelle
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showNorthArrow} onChange={(e) => patch({ showNorthArrow: e.target.checked })} />
        Flèche nord
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Cartouche
        <textarea value={current.cartouche ?? ""} onChange={(e) => patch({ cartouche: e.target.value || null })} />
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/builder/print/PrintLayoutPanel.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Intégrer dans `MapEditorPage.tsx`**

Ajouter l'import et un setter fonctionnel (même patron que `setStyle`/`setLayers` déjà présents), puis monter le panneau dans l'aside, après `LayersPanel` et avant le bouton « Enregistrer » :

```tsx
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
// ...
function setPrintLayout(printLayout: PrintLayoutConfig | null) {
  setDraft((d) => (d ? { ...d, printLayout } : d));
}
// ... dans le JSX de l'aside :
<PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
```

Inspecter la forme exacte de `setStyle`/`setLayers` dans `MapEditorPage.tsx` avant d'écrire `setPrintLayout` pour rester rigoureusement cohérent avec leur patron (spread fonctionnel sur `setDraft`, garde `d ?`).

- [ ] **Step 6: Intégrer dans `AppBuilderPage.tsx`**

Même patron, monté dans l'aside `mode === "edit"`, à la suite de la section Thème :

```tsx
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
// ...
function setPrintLayout(printLayout: PrintLayoutConfig | null) {
  setDraft((d) => (d ? { ...d, printLayout } : d));
}
// ...
<p className="mb-1 mt-3 text-xs font-medium text-slate-500">Impression</p>
<PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
```

- [ ] **Step 7: Test de régression du round-trip complet (map)**

Ajouter à `shell/src/pages/MapEditorPage.test.tsx` (mirroir du style des tests déjà présents dans ce fichier — inspecter avant d'écrire) :

```tsx
it("saving after only changing a layer keeps the previously loaded printLayout", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  const client: Partial<ItemClient> = {
    getMapConfig: vi.fn().mockResolvedValue({
      basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [],
      printLayout: { pageSize: "a3", orientation: "landscape" },
    }),
    saveMapConfig,
  };
  renderMapEditorPage({ client, pk: "pk-1" });
  await screen.findByText(/A3/i); // le panneau reflète bien le printLayout chargé
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const [, savedConfig] = saveMapConfig.mock.calls[0];
  expect(savedConfig.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
});
```

Adapter `renderMapEditorPage`/le nom exact du helper de rendu déjà présent dans `MapEditorPage.test.tsx`.

- [ ] **Step 8: Vérifier build + tests shell complets**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx src/pages/AppBuilderPage.test.tsx && npm run build`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/print/PrintLayoutPanel.tsx shell/src/builder/print/PrintLayoutPanel.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): SP-17a — PrintLayoutPanel intégré aux builders carte/app"
```

---

### Task 10: Mode `exportRender` (chrome d'impression + signal de disponibilité)

> Playwright attend `[data-export-ready="true"]` (posé par la tâche 6 côté cœur) avant de capturer — sans ce signal réel, la capture se ferait sur une page vide/tuiles non chargées. Pour la carte, le signal est l'événement MapLibre `idle` (aucun délai fixe). Pour l'app/dashboard, en l'absence d'un signal par-widget instrumenté (hors périmètre 17a — scope documenté), le signal est « la requête de config a réussi + une frame de peinture » — un signal réel (succès de requête + paint), pas un minuteur arbitraire, mais moins rigoureux que le cas carte pour des widgets non-cartographiques ; documenté comme limite connue plutôt que silencieusement passé sous silence.

**Files:**
- Create: `shell/src/shell/exportReady.ts`
- Create: `shell/src/shell/useIsExportRender.ts`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/map/MapView.test.tsx`, `shell/src/shell/useIsExportRender.test.ts`

**Interfaces:**
- Produces: `markExportReady(): void` (idempotent, pose `document.body.dataset.exportReady = "true"`). `useIsExportRender(): boolean` (lit `useSearchParams().get("exportRender") === "1"`). `MapView` gagne une prop `onReady?: () => void`, appelée dans `map.once("idle", ...)`.

- [ ] **Step 1: Écrire le test de `useIsExportRender`, qui échoue**

```typescript
// shell/src/shell/useIsExportRender.test.ts
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useIsExportRender } from "./useIsExportRender";

function wrapper(initialPath: string) {
  return ({ children }: { children: React.ReactNode }) => <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>;
}

describe("useIsExportRender", () => {
  it("is false without the query param", () => {
    const { result } = renderHook(() => useIsExportRender(), { wrapper: wrapper("/maps/1") });
    expect(result.current).toBe(false);
  });

  it("is true with exportRender=1", () => {
    const { result } = renderHook(() => useIsExportRender(), { wrapper: wrapper("/maps/1?exportRender=1") });
    expect(result.current).toBe(true);
  });
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/shell/useIsExportRender.test.ts`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implémenter `useIsExportRender` et `exportReady`**

```typescript
// shell/src/shell/useIsExportRender.ts
import { useSearchParams } from "react-router-dom";

export function useIsExportRender(): boolean {
  const [params] = useSearchParams();
  return params.get("exportRender") === "1";
}
```

```typescript
// shell/src/shell/exportReady.ts
// Signal DOM que le worker Playwright (core/app/export/jobs.py) attend via
// page.wait_for_selector('[data-export-ready="true"]') avant de capturer.
// Idempotent : peut être appelé plusieurs fois sans effet de bord.
export function markExportReady(): void {
  document.body.dataset.exportReady = "true";
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/shell/useIsExportRender.test.ts`
Expected: PASS

- [ ] **Step 5: Écrire le test de `MapView`, qui échoue**

Ajouter à `shell/src/map/MapView.test.tsx` (inspecter le fichier existant pour le style exact de mock de `maplibre-gl` déjà en place — probablement un mock du module entier avec un faux `Map` émettant des événements) :

```tsx
it("calls onReady once the map fires 'idle'", async () => {
  const onReady = vi.fn();
  const { mapInstance } = renderMapView({ onReady }); // helper existant du fichier, à adapter
  mapInstance.emit("load");
  mapInstance.emit("idle");
  expect(onReady).toHaveBeenCalledTimes(1);
});
```

Adapter précisément au harnais de mock déjà utilisé dans ce fichier de test (nom du helper de rendu, façon d'émettre un événement sur le faux `maplibregl.Map`) — ne pas réinventer un mock parallèle.

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL — prop `onReady` ignorée.

- [ ] **Step 7: Implémenter dans `MapView.tsx`**

Ajouter `onReady?: () => void` à la liste de props du composant (même endroit que `onViewChange`/`onFeatureClick`), un ref stable comme pour les autres callbacks (lignes 129-137), et l'appel dans le handler `load` existant (ligne 154-159) :

```tsx
  const onReadyRef = useRef(onReady);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
```

Dans le `map.on("load", () => { ... })` existant, ajouter à la fin du callback :

```tsx
      map.once("idle", () => onReadyRef.current?.());
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS

- [ ] **Step 9: Mode `exportRender` dans `MapEditorPage.tsx`**

```tsx
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
// ...
const isExportRender = useIsExportRender();
// ...
if (isExportRender) {
  return (
    <div className="relative h-full w-full">
      <MapView config={draft} onReady={markExportReady} />
      {draft.printLayout?.title && (
        <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">{draft.printLayout.title}</div>
      )}
      {draft.printLayout?.showLegend && (
        <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
          {draft.layers.filter((l) => l.visible).map((l) => <li key={l.id}>{l.title}</li>)}
        </ul>
      )}
      {draft.printLayout?.cartouche && (
        <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">{draft.printLayout.cartouche}</div>
      )}
    </div>
  );
}
// ... suivi du rendu normal du builder existant
```

Placer ce retour anticipé juste après que `draft` soit garanti non-null (après la garde de chargement existante), avant le rendu normal de l'aside/MapView. La barre d'échelle (`showScaleBar`) et la flèche nord (`showNorthArrow`) sont volontairement **non implémentées visuellement dans cette tâche** — cases conservées dans `PrintLayoutPanel` pour la forme du schéma (accepté par le design), mais leur rendu réel (contrôle MapLibre `ScaleControl` / icône SVG positionnée) est un raffinement futur non bloquant, à documenter comme tel dans le rapport de tâche plutôt que rendu silencieusement inopérant sans trace.

- [ ] **Step 10: Mode `exportRender` dans `AppRuntimePage.tsx`**

```tsx
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
// ...
const isExportRender = useIsExportRender();
const appQuery = useAppConfig(pk, { mode: "runtime" });
useEffect(() => {
  if (isExportRender && appQuery.isSuccess) {
    requestAnimationFrame(() => markExportReady());
  }
}, [isExportRender, appQuery.isSuccess]);
```

Et, dans le JSX, entourer la barre d'actions existante (« Enregistrer la vue », futur bouton « Exporter » de la Tâche 11) d'une garde `{!isExportRender && ( ... )}` pour qu'elle n'apparaisse pas dans la capture.

- [ ] **Step 11: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS, aucune régression.

- [ ] **Step 12: Commit**

```bash
git add shell/src/shell/exportReady.ts shell/src/shell/useIsExportRender.ts shell/src/shell/useIsExportRender.test.ts shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): SP-17a — mode exportRender (chrome PrintLayout + signal data-export-ready)"
```

---

### Task 11: `ExportPanel` (bouton + dialogue + poll) + intégration

**Files:**
- Create: `shell/src/builder/print/ExportPanel.tsx`
- Create: `shell/src/builder/print/ExportPanel.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`

**Interfaces:**
- Consumes: `itemClient.createExport`/`getExportJob` (Tâche 8), `useInstanceInfo` (Tâche 2).
- Produces: `ExportPanel({ itemId }: { itemId: string })` — bouton « Exporter », dialogue de choix de format, poll (patron `PipelineRunPanel`), lien de téléchargement une fois `done`, message d'erreur `role="alert"` si `error` ou si l'appel initial échoue.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/builder/print/ExportPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ItemClientProvider } from "../../api/ItemClientProvider"; // adapter au nom réel du provider utilisé par PipelineRunPanel.test.tsx
import { ExportPanel } from "./ExportPanel";
import type { ItemClient } from "../../api/itemClient";

function renderPanel(client: Partial<ItemClient>) {
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <ExportPanel itemId="item-1" />
    </ItemClientProvider>,
  );
}

describe("ExportPanel", () => {
  it("creates an export job on click and polls until done, then shows a download link", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    let call = 0;
    const getExportJob = vi.fn().mockImplementation(() => {
      call += 1;
      const status = call < 2 ? "running" : "done";
      return Promise.resolve({ id: "job-1", status, resultUrl: status === "done" ? "https://minio.test/x.pdf" : null, error: null });
    });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    expect(createExport).toHaveBeenCalledWith("item-1", "pdf");
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toHaveAttribute("href", "https://minio.test/x.pdf"), { timeout: 5000 });
    expect(call).toBeGreaterThanOrEqual(2);
  });

  it("surfaces a job error via role=alert instead of silently stopping", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi.fn().mockResolvedValue({ id: "job-1", status: "error", resultUrl: null, error: "render timeout" });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PNG" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("render timeout"));
  });

  it("surfaces a failure to even create the job", async () => {
    const createExport = vi.fn().mockRejectedValue(new Error("Request failed: 403 POST /export"));
    renderPanel({ createExport, getExportJob: vi.fn() });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
  });
});
```

Vérifier le nom exact du provider React exposant `ItemClient` au reste de l'arbre (utilisé par `PipelineRunPanel.test.tsx`) avant d'écrire ce test, et l'aligner précisément.

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implémenter**

```tsx
// shell/src/builder/print/ExportPanel.tsx
import { useState } from "react";
import { useItemClientInternal } from "../../api/hooks";
import type { ExportFormat, ExportJob } from "../../api/types";

const POLL_INTERVAL_MS = 1500;

export function ExportPanel({ itemId }: { itemId: string }) {
  const client = useItemClientInternal();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function poll(jobId: string) {
    for (;;) {
      const latest = await client.getExportJob(jobId);
      setJob(latest);
      if (latest.status !== "pending" && latest.status !== "running") return;
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
  }

  async function onExport(format: ExportFormat) {
    setDialogOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createExport(itemId, format);
      await poll(jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de l'export.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button type="button" onClick={() => setDialogOpen(true)} disabled={running}>
        Exporter
      </button>
      {dialogOpen && (
        <div role="dialog" aria-label="Choisir le format d'export" className="flex gap-2">
          <button type="button" onClick={() => onExport("png")}>PNG</button>
          <button type="button" onClick={() => onExport("pdf")}>PDF</button>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a role="link" href={job.resultUrl} download>
          Télécharger l'export
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert">{error ?? job?.error ?? "Échec de l'export."}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Intégrer dans `MapEditorPage.tsx`**

Ajouter, gardé par la capacité `exportEnabled` (`useInstanceInfo()`, même patron que `etlEnabled` dans `NewItemButton.tsx`), dans l'aside du mode édition normal (pas dans la branche `isExportRender` de la Tâche 10) :

```tsx
import { ExportPanel } from "../builder/print/ExportPanel";
import { useInstanceInfo } from "../api/hooks";
// ...
const instanceQuery = useInstanceInfo();
const exportEnabled = instanceQuery.data?.exportEnabled === true;
// ... dans l'aside, à la suite de PrintLayoutPanel :
{pk !== null && exportEnabled && <ExportPanel itemId={pk} />}
```

- [ ] **Step 6: Intégrer dans `AppRuntimePage.tsx`**

Dans la barre du haut déjà gardée par `{!isExportRender && ( ... )}` (Tâche 10), à côté du bouton « Enregistrer la vue » :

```tsx
import { ExportPanel } from "../builder/print/ExportPanel";
import { useInstanceInfo } from "../api/hooks";
// ...
const instanceQuery = useInstanceInfo();
const exportEnabled = instanceQuery.data?.exportEnabled === true;
// ...
{exportEnabled && <ExportPanel itemId={pk} />}
```

- [ ] **Step 7: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/print/ExportPanel.tsx shell/src/builder/print/ExportPanel.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): SP-17a — ExportPanel (bouton, dialogue, poll) intégré carte/app"
```

---

### Task 12: Bootstrap d'auth — dérogation `exportToken`

**Files:**
- Modify: `shell/src/auth/useAuth.ts`
- Modify: `shell/src/auth/RequireAuth.tsx`
- Modify: `shell/src/App.tsx` (câblage de `getToken`)
- Test: `shell/src/auth/RequireAuth.test.tsx`

**Interfaces:**
- Produces: `RequireAuth` ne redirige plus vers Keycloak quand `?exportToken=...` est présent dans l'URL. `getToken` (passé à `createItemClient`) renvoie l'`exportToken` de l'URL en priorité s'il est présent, sinon le jeton OIDC/mock normal.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/auth/RequireAuth.test.tsx (ajouter aux tests existants du fichier)
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { RequireAuth } from "./RequireAuth";

it("renders children without triggering signIn when exportToken is present, even though not authenticated", () => {
  // Mock useAuth pour renvoyer isAuthenticated=false et une fonction signIn
  // qui, si elle est appelée, fait échouer le test — adapter au mock déjà
  // utilisé par les tests existants de ce fichier (vi.mock("./useAuth", ...)).
  render(
    <MemoryRouter initialEntries={["/maps/1?exportToken=abc123"]}>
      <RequireAuth>
        <div>contenu protégé</div>
      </RequireAuth>
    </MemoryRouter>,
  );
  expect(screen.getByText("contenu protégé")).toBeInTheDocument();
});
```

Inspecter le mock de `useAuth` déjà présent dans `RequireAuth.test.tsx` avant d'écrire ce test — l'assertion "signIn jamais appelé" doit réutiliser le même spy que les tests existants (ex. `expect(signIn).not.toHaveBeenCalled()`), pas un nouveau mock parallèle.

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/auth/RequireAuth.test.tsx`
Expected: FAIL — `RequireAuth` déclenche `signIn()` (redirection), le contenu protégé ne s'affiche jamais.

- [ ] **Step 3: Implémenter**

Dans `RequireAuth.tsx`, en tête du composant, avant l'effet qui appelle `signIn()` :

```tsx
import { useSearchParams } from "react-router-dom";
// ...
const [searchParams] = useSearchParams();
const hasExportToken = searchParams.get("exportToken") !== null;
```

Dans l'`useEffect` existant qui déclenche `signIn()` sur `!isLoading && !isAuthenticated && !error`, ajouter `hasExportToken` à la garde négative (`&& !hasExportToken`), et dans la condition de rendu qui bloque les enfants (`return null` tant que non authentifié), ajouter `|| hasExportToken` pour laisser passer :

```tsx
useEffect(() => {
  if (!isLoading && !isAuthenticated && !error && !hasExportToken) {
    signIn();
  }
}, [isLoading, isAuthenticated, error, hasExportToken, signIn]);

if (!hasExportToken && (isLoading || (!isAuthenticated && !error))) {
  return null;
}

return <>{children}</>;
```

Adapter précisément à la structure conditionnelle réelle déjà présente dans `RequireAuth.tsx` (inspecter le fichier avant d'éditer) — le principe est : la présence d'`exportToken` dans l'URL doit être une porte de sortie anticipée qui court-circuite à la fois le déclenchement de `signIn()` et le blocage du rendu des enfants.

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/auth/RequireAuth.test.tsx`
Expected: PASS

- [ ] **Step 5: Câbler `getToken` pour préférer `exportToken`**

Dans `shell/src/App.tsx` (ou le fichier exact qui construit `getToken` et l'injecte dans `createItemClient({ coreUrl, martinUrl, getToken })` — confirmer l'emplacement précis en inspectant `App.tsx` avant d'éditer), remplacer :

```tsx
getToken: getAccessToken,
```

par une fonction qui préfère l'`exportToken` d'URL :

```tsx
function useExportAwareToken(getAccessToken: () => string | undefined) {
  const [searchParams] = useSearchParams();
  const exportToken = searchParams.get("exportToken");
  return () => exportToken ?? getAccessToken();
}
// ...
getToken: useExportAwareToken(getAccessToken),
```

Ajuster la syntaxe exacte pour respecter les règles des hooks React (l'appel de `useSearchParams` doit se faire au niveau du composant qui construit `createItemClient`, pas conditionnellement) — inspecter la structure réelle de `App.tsx` pour placer cette logique au bon endroit (probablement dans le composant qui appelle déjà `useAuth()` pour obtenir `getAccessToken`).

- [ ] **Step 6: Test manuel de bout en bout du bootstrap**

Run: `cd shell && npm run dev` puis dans un navigateur, avec `VITE_AUTH_MODE=mock` (mode dev par défaut de ce dépôt), naviguer vers `/maps/<un-id-existant>?exportToken=fake&exportRender=1` sans être connecté au préalable.
Expected: la page se charge sans redirection vers Keycloak (mode mock ne redirige déjà pas normalement — vérifier plutôt en simulant `VITE_AUTH_MODE=oidc` localement si la config le permet ; sinon se contenter de la couverture par tests unitaires ci-dessus et noter dans le rapport de tâche que la vérification manuelle en mode OIDC réel n'a pas pu être faite dans cet environnement).

- [ ] **Step 7: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add shell/src/auth/useAuth.ts shell/src/auth/RequireAuth.tsx shell/src/auth/RequireAuth.test.tsx shell/src/App.tsx
git commit -m "feat(shell): SP-17a — bootstrap d'auth : dérogation exportToken pour le rendu Playwright"
```

---

### Task 13: Infra — `export-worker` (Dockerfile, compose, import-linter, dépendances)

**Files:**
- Create: `deploy/export-worker/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `core/app/jobs.py`
- Modify: `core/pyproject.toml` (`[tool.importlinter]`)
- Modify: `.env.example`

**Interfaces:**
- Produces: service compose `export-worker` (profil `export`), tâche `app.export.jobs` connue du worker dédié, `app.export` dans le contrat de couches.

- [ ] **Step 1: Ajouter `app.export.jobs` aux `import_paths` de procrastinate**

Dans `core/app/jobs.py`, ligne 59-62, remplacer :

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
    ],
```

par :

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs",
    ],
```

- [ ] **Step 2: Vérifier le test existant de `import_paths`**

Run: `cd core && uv run pytest tests/test_jobs.py -v`
Expected: PASS — `test_import_paths_registers_all_domain_tasks` (mentionné dans le docstring de `app/jobs.py`) doit continuer à passer ; s'il itère sur une liste figée de modules attendus plutôt que de dériver dynamiquement, l'étendre pour inclure `app.export.jobs` (inspecter le test avant de conclure qu'aucun changement n'y est nécessaire).

- [ ] **Step 3: Ajouter `app.export` au contrat de couches import-linter**

Dans `core/pyproject.toml`, section `[[tool.importlinter.contracts]] layers = [...]` (lignes 98-118), insérer `"app.export"` juste après `"app.alerts",` :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.alerts",
    "app.export",
    "app.secrets",
    "app.ingestion",
    ...
]
```

Et dans `ignore_imports`, ajouter :

```toml
    "app.db -> app.export.models",
```

- [ ] **Step 4: Vérifier import-linter**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept.` (ou équivalent « aucune violation ») — si une violation apparaît (ex. `app.export -> app.pipelines` inattendu), c'est le signal qu'un import a été mal placé dans une tâche précédente ; corriger l'import fautif plutôt que déplacer `app.export` dans la liste des couches.

- [ ] **Step 5: Dockerfile de l'export-worker**

```dockerfile
# deploy/export-worker/Dockerfile
# Miroir de core/Dockerfile (même dépendances, mêmes extensions DuckDB
# préinstallées) + Chromium Playwright. Volontairement un Dockerfile séparé
# plutôt qu'ajouter Playwright à core/Dockerfile : le binaire Chromium avec
# ses dépendances système pèse plusieurs centaines de Mo, que ni `core` ni
# le `worker` partagé (ingestion/search/cdc/etl) n'ont besoin de porter
# (SP-17a, design §Infrastructure — même rationale que deploy/qgis-worker,
# à ceci près que la raison ici est le poids de l'image, pas une licence).
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

CMD ["python", "-m", "procrastinate", "--app", "app.jobs.app", "worker", "-q", "export"]
```

- [ ] **Step 6: Service compose `export-worker`**

Dans `docker-compose.yml`, insérer après le bloc `qgis-worker` (après la ligne `restart: unless-stopped` du service `qgis-worker`, avant le commentaire du `cdc-worker`) :

```yaml
  # Worker d'export Playwright (SP-17a, A25) — image dédiée (Chromium +
  # dépendances système), séparée du worker partagé pour ne pas l'alourdir
  # pour tout le monde. Profil `export` : un `docker compose up` par défaut
  # ne le démarre pas, même porte que CORE_EXPORT_ENABLED. Aucun volume
  # partagé requis : le rendu (screenshot/PDF) reste en mémoire, upload S3
  # direct — pas d'intermédiaire disque comme etl-scratch.
  export-worker:
    build:
      context: ./core
      dockerfile: ../deploy/export-worker/Dockerfile
    profiles: ["export"]
    command: python -m procrastinate --app app.jobs.app worker -q export
    environment:
      DATABASE_URL: postgresql+psycopg://gis:${PG_PASSWORD}@pgbouncer:6432/gis
      S3_ENDPOINT_URL: http://minio:9000
      S3_ACCESS_KEY: ${MINIO_USER}
      S3_SECRET_KEY: ${MINIO_PASSWORD}
      S3_EXPORTS_BUCKET: geostudio-exports
      CORE_EXPORT_ENABLED: "true"
      CORE_EXPORT_TOKEN_SECRET: ${CORE_EXPORT_TOKEN_SECRET}
      SHELL_BASE_URL: http://shell:8300
    networks: [gis-net]
    depends_on: [pgbouncer, minio]
    restart: unless-stopped
```

- [ ] **Step 7: Documenter `SHELL_BASE_URL` dans `.env.example`**

Après le bloc `CORE_EXPORT_TOKEN_SECRET` ajouté Tâche 4 :

```
# URL interne (réseau docker) du service shell, utilisée UNIQUEMENT par
# export-worker pour naviguer vers la page runtime à exporter — jamais
# exposée publiquement. Le défaut du docker-compose.yml (http://shell:8300)
# suffit en développement ; à ne surcharger qu'en déploiement où le service
# shell n'est pas nommé "shell" sur le réseau docker.
SHELL_BASE_URL=http://shell:8300
```

- [ ] **Step 8: Valider la config compose**

Run: `docker compose --profile export config -q`
Expected: aucune erreur de syntaxe/référence (ne lance rien, valide juste le YAML résolu).

- [ ] **Step 9: Build réel de l'image (best-effort, non bloquant si l'environnement n'a pas accès réseau à un registre Chromium)**

Run: `docker compose --profile export build export-worker`
Expected: build réussi. Si l'environnement de la tâche ne permet pas de builder une image Docker (pas de démon Docker accessible, pas d'accès réseau sortant), **documenter cet état exact dans le rapport de tâche** plutôt que de prétendre l'avoir vérifié — cf. le précédent des tests `@pytest.mark.qgis` de SP-15d jamais exécutés pour de vrai, qui a laissé une trace honnête plutôt qu'une fausse affirmation de succès.

- [ ] **Step 10: Commit**

```bash
git add deploy/export-worker/Dockerfile docker-compose.yml core/app/jobs.py core/pyproject.toml .env.example
git commit -m "feat(infra): SP-17a — conteneur export-worker (profil export) + contrat de couches"
```

---

### Task 14: E2E — export depuis la visionneuse de carte

**Files:**
- Create: `shell/e2e/export.spec.ts`

**Interfaces:**
- Consumes: toute la chaîne des tâches 1-13, via interception réseau Playwright (pas de vrai cœur/worker démarré — cohérent avec les 13+ specs E2E existantes qui tournent contre `VITE_AUTH_MODE=mock` + interception de routes).

- [ ] **Step 1: Écrire la spec**

Inspecter d'abord `shell/e2e/pipeline-builder.spec.ts` ou `shell/e2e/alert-rule.spec.ts` (cités dans le design comme référence de profondeur d'assertion) pour le patron exact d'authentification mock + navigation + `page.route(...)` déjà en place dans ce dépôt, puis écrire :

```typescript
// shell/e2e/export.spec.ts
import { test, expect } from "@playwright/test";

test("exporter une carte en PDF depuis la visionneuse : le job atteint 'done' et expose un lien de téléchargement", async ({ page }) => {
  let createdExportBody: unknown = null;
  let pollCount = 0;

  await page.route("**/instance", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ readOnly: false, etlEnabled: false, exportEnabled: true }) }),
  );

  await page.route("**/configs/by-item/*", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ config: { kind: "map", map: { basemap: { style: "https://demotiles.maplibre.org/style.json" }, view: { center: [0, 0], zoom: 2 }, layers: [] } } }),
    });
  });

  await page.route("**/export", async (route) => {
    createdExportBody = route.request().postDataJSON();
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ jobId: "job-e2e-1" }) });
  });

  await page.route("**/export/jobs/job-e2e-1", async (route) => {
    pollCount += 1;
    const status = pollCount < 2 ? "running" : "done";
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: "job-e2e-1", status, resultUrl: status === "done" ? "https://minio.example.test/exports/job-e2e-1.pdf" : null, error: null }),
    });
  });

  await page.goto("/maps/map-1");
  await page.getByRole("button", { name: "Exporter" }).click();
  await page.getByRole("button", { name: "PDF" }).click();

  await expect.poll(() => createdExportBody).not.toBeNull();
  // Vérifie le CONTENU du POST, pas seulement qu'un POST a eu lieu (piège
  // documenté CLAUDE.md/SP-16b : une assertion finale qui ne prouve qu'une
  // occurrence sans vérifier le corps).
  expect(createdExportBody).toEqual({ itemId: "map-1", format: "pdf" });

  const downloadLink = page.getByRole("link", { name: /télécharger/i });
  await expect(downloadLink).toHaveAttribute("href", "https://minio.example.test/exports/job-e2e-1.pdf", { timeout: 10_000 });
  expect(pollCount).toBeGreaterThanOrEqual(2);
});

test("le bouton Exporter est absent quand la capacité est désactivée", async ({ page }) => {
  await page.route("**/instance", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ readOnly: false, etlEnabled: false, exportEnabled: false }) }),
  );
  await page.route("**/configs/by-item/*", (route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ config: { kind: "map", map: { basemap: { style: "https://demotiles.maplibre.org/style.json" }, view: { center: [0, 0], zoom: 2 }, layers: [] } } }),
    }),
  );

  await page.goto("/maps/map-1");
  await expect(page.getByRole("button", { name: "Exporter" })).toHaveCount(0);
});
```

Adapter l'URL de navigation initiale (`/maps/map-1`) et le mécanisme d'authentification mock au patron réel déjà utilisé par les autres specs E2E de ce dépôt (probablement une étape de login/bypass en amont dans un `beforeEach` partagé — inspecter `shell/e2e/pipeline-builder.spec.ts` pour le reproduire à l'identique).

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/export.spec.ts`
Expected: PASS (2 tests). Si le premier test échoue sur le sélecteur du bouton PDF (texte exact différent de celui posé Tâche 11), ajuster la spec pour matcher le texte réel du bouton — ne jamais assouplir l'assertion sur le corps du POST pour faire passer le test.

- [ ] **Step 3: Suite E2E complète (non-régression)**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: PASS — les 13+ specs existantes restent vertes en plus de `export.spec.ts`.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/export.spec.ts
git commit -m "test(e2e): SP-17a — exporter une carte en PDF, capacité désactivée cache le bouton"
```

---

## Après l'exécution

Une fois les 14 tâches livrées et review passée : mettre à jour `CLAUDE.md` (nouvelle entrée SP-17a dans « Fait », déplacer la ligne SP-17 de « À venir » vers son état réel — 3D et `ReportSchedule` restent à faire) et la mémoire de session, en documentant explicitement l'état réel des deux vérifications best-effort non bloquantes (test `@pytest.mark.playwright` de la Tâche 6, build Docker de la Tâche 13) — jamais une affirmation de succès non vérifiée, cf. le précédent SP-15d.
