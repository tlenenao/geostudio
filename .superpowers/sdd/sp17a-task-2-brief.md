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

