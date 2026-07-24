### Task 1 : fixer la boucle de redémarrage du `worker` (bloqueur 1)

**Files:**
- Create: `core/scripts/ensure_procrastinate_schema.py`
- Create: `core/tests/test_ensure_procrastinate_schema.py`
- Modify: `docker-compose.yml:162-164` (service `worker`, base compose — ce fix bénéficie au dev comme au prod, pas seulement à `docker-compose.prod.yml`)

**Interfaces:**
- Consumes: `app.jobs.app` (module existant, inchangé) ; fixture `pg_engine` de `core/tests/conftest.py` (existante).
- Produces: `scripts.ensure_procrastinate_schema.schema_is_applied(conninfo: str) -> bool`, `scripts.ensure_procrastinate_schema.main() -> None` — invocable via `python -m scripts.ensure_procrastinate_schema` (lit `DATABASE_URL` dans l'environnement, même variable que le reste du service `worker`).

**Contexte vérifié en lisant le code :**
- `core/tests/conftest.py::pg_engine_with_procrastinate_schema` documente déjà exactement ce bug : *"`apply_schema()` n'est PAS idempotente — un second appel sur une base où le schéma existe déjà lève (`CREATE TYPE` échoue)"* — et le contourne avec une garde `sa_inspect(pg_engine).has_table("procrastinate_jobs")`. Ce script réutilise la même garde, en dehors de pytest.
- `core/scripts/__init__.py` existe déjà (le module `scripts` est importable via `-m`, patron déjà utilisé par `python -m scripts.seed_demo`, documenté dans `docs/superpowers/plans/2026-07-16-sp9-install-secrets.md`).
- `core/Dockerfile` copie déjà `COPY scripts ./scripts` (fait en SP-9-install) — **aucune modification du Dockerfile n'est nécessaire**, le nouveau script sera automatiquement présent dans l'image `core`/`worker` (même image, `build: ./core`).
- `core/app/jobs.py` définit `app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=_conninfo()), ...)` — le script ci-dessous n'importe **pas** `app.jobs.app` (ça déclencherait tout l'`import_paths` et l'enregistrement des tâches métier, inutile ici) ; il construit sa propre `procrastinate.App` minimale, seulement pour appeler `schema_manager.apply_schema()`, exactement comme le fait déjà `pg_engine_with_procrastinate_schema`.

- [ ] **Step 1: Écrire le test (rouge)**

Créer `core/tests/test_ensure_procrastinate_schema.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from scripts.ensure_procrastinate_schema import main, schema_is_applied


@pytest.mark.postgis
def test_running_main_twice_never_raises(pg_engine, monkeypatch):
    """Régression du bloqueur SP-Deploy §3.4-1 : avant ce fix, appeler
    `apply_schema()` une seconde fois sur une base où le schéma existe déjà
    levait (`CREATE TYPE` échoue), ce qui faisait boucler le service
    `worker` en redémarrage (`schema --apply && worker`, relancé en entier
    par `restart: unless-stopped` à chaque crash). `main()` doit être
    rejouable sans exception, quel que soit l'état de départ."""
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])

    main()
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    assert schema_is_applied(conninfo)

    main()  # deuxième appel — ne doit PAS lever


@pytest.mark.postgis
def test_schema_is_applied_reflects_real_state(pg_engine):
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    # pg_engine (session-scope) peut déjà avoir le schéma appliqué par un
    # autre test de la suite (pg_engine_with_procrastinate_schema) — on
    # vérifie seulement la cohérence du prédicat, pas un état "avant/après"
    # isolé (la base de test est partagée, comme pour cette fixture sœur).
    assert schema_is_applied(conninfo) in (True, False)
```

- [ ] **Step 2: Vérifier que le test échoue (module absent)**

```bash
cd core && uv run pytest tests/test_ensure_procrastinate_schema.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'scripts.ensure_procrastinate_schema'` (ou `ImportError` équivalent) — sans `CORE_TEST_DATABASE_URL`, les deux tests sont de toute façon skippés (`pg_engine` lève `pytest.skip`), mais l'échec de collection (import cassé) doit apparaître avant même le skip.

- [ ] **Step 3: Écrire l'implémentation**

Créer `core/scripts/ensure_procrastinate_schema.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Applique le schéma procrastinate (table `procrastinate_jobs` et
dépendances) une seule fois. `SchemaManager.apply_schema()` n'est PAS
idempotente (`CREATE TYPE` échoue au second appel sur une base où le schéma
existe déjà) — ce qui faisait boucler le service `worker` en redémarrage
sous `docker-compose.yml` (`schema --apply && worker`, relancé en entier
par `restart: unless-stopped` à chaque crash, cf. CLAUDE.md « suivis non
bloquants »). Ce script se substitue à `procrastinate schema --apply` dans
le `command:` du worker : il vérifie d'abord si le schéma est déjà là
(`has_table`) et ne rappelle `apply_schema()` que s'il est absent — même
garde que `core/tests/conftest.py::pg_engine_with_procrastinate_schema`."""
import os
import sys

import procrastinate
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect


def schema_is_applied(conninfo: str) -> bool:
    engine = create_engine(conninfo)
    try:
        return sa_inspect(engine).has_table("procrastinate_jobs")
    finally:
        engine.dispose()


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    if schema_is_applied(database_url):
        print("procrastinate: schéma déjà appliqué, rien à faire.")
        return
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=database_url)
    )
    with app.open():
        app.schema_manager.apply_schema()
    print("procrastinate: schéma appliqué.")


if __name__ == "__main__":
    main()
    sys.exit(0)
```

- [ ] **Step 4: Lancer les tests (nécessite un vrai PostGIS)**

```bash
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis \
  uv run pytest tests/test_ensure_procrastinate_schema.py -v -m postgis
```

Expected: `2 passed`. Si aucun PostGIS n'est disponible localement, démarrer temporairement celui du compose (`docker compose up -d postgis`, DSN `postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis` — le port `5432` n'est pas publié par défaut dans `docker-compose.yml` : ajouter ponctuellement `docker compose exec postgis psql ...` ou publier le port le temps du test, puis le retirer — ne pas laisser un `ports:` supplémentaire trainer dans le compose commité).

- [ ] **Step 5: Suite complète + lint (non-régression)**

```bash
cd core && uv run pytest && uv run lint-imports
```

Expected: tous verts (nouveau fichier `core/scripts/ensure_procrastinate_schema.py` n'importe que `procrastinate`/`sqlalchemy`, des libs tierces hors contrat de frontières — `lint-imports` reste 1 kept / 0 broken).

- [ ] **Step 6: Brancher le script dans le `command:` du service `worker`**

Modifier `docker-compose.yml` — remplacer :

```yaml
    command: >
      sh -c "python -m procrastinate --app app.jobs.app schema --apply &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc"
```

par :

```yaml
    command: >
      sh -c "python -m scripts.ensure_procrastinate_schema &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc"
```

- [ ] **Step 7: Valider la syntaxe du compose**

```bash
./scripts/bootstrap-env.sh
docker compose config >/dev/null && echo "compose config OK"
rm -f .env
```

- [ ] **Step 8: Vérifier réellement l'absence de boucle (bout-en-bout)**

```bash
docker compose up -d postgis pgbouncer minio
docker compose up -d worker
sleep 5
docker compose ps worker
```

Expected: `worker` en `Up` (pas de colonne `Restarting`).

```bash
docker compose restart worker
sleep 5
docker compose logs worker --tail 20
docker compose ps worker
```

Expected : aucune trace `Traceback`/`DuplicateObject`/`CREATE TYPE` dans les logs, `worker` de nouveau `Up` — preuve que le second passage (schéma déjà appliqué) ne relève plus l'erreur qui causait la boucle.

```bash
docker compose down
```

- [ ] **Step 9: Commit**

```bash
git add core/scripts/ensure_procrastinate_schema.py core/tests/test_ensure_procrastinate_schema.py docker-compose.yml
git commit -m "fix(core): worker — schéma procrastinate idempotent (fin de la boucle de redémarrage)"
```

---

