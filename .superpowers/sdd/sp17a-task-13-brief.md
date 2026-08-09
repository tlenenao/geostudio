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

