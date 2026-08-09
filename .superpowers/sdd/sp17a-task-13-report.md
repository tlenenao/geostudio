# SP-17a Task 13 — Rapport : infra `export-worker`

Commit : `cf20c72` — `feat(infra): SP-17a — conteneur export-worker (profil export) + contrat de couches`

## Ce qui a été fait

1. **`core/app/jobs.py`** : ajout de `"app.export.jobs"` à `import_paths` de
   `procrastinate.App`, après `"app.alerts.jobs"` (ligne 62).
2. **`core/tests/test_jobs.py`** : **aucun changement**. Inspection faite
   avant de conclure : `test_import_paths_registers_all_domain_tasks`
   n'assert que sur un sous-ensemble fixe de noms de tâches (ingestion,
   items, collections, cdc, harvest) — ni `app.pipelines.jobs` ni
   `app.alerts.jobs`, pourtant déjà dans `import_paths` depuis SP-15/SP-16b,
   n'ont d'assertion dédiée. Le test vérifie une présence, pas une liste
   exhaustive/fermée : il n'aurait pas échoué même sans le fix de Step 1, et
   ajouter une assertion pour `app.export.jobs` suivrait un précédent que le
   code existant ne suit déjà pas lui-même. Décision : pas d'extension,
   cohérent avec l'historique du fichier. Test lancé et vert (3 passed).
3. **`core/pyproject.toml`** : `"app.export"` inséré dans `layers` juste
   après `"app.alerts",` ; `"app.db -> app.export.models"` ajouté à
   `ignore_imports` (dernière ligne, après `app.secrets.models`).
4. **`deploy/export-worker/Dockerfile`** (nouveau) : créé exactement comme
   spécifié dans le brief — miroir de `core/Dockerfile` (mêmes étapes `uv
   pip install`, mêmes extensions DuckDB préinstallées) + `playwright
   install --with-deps chromium`, `CMD` sur la queue `export`.
5. **`docker-compose.yml`** : service `export-worker` inséré après le bloc
   `qgis-worker` (`restart: unless-stopped`), avant le commentaire du bloc
   `cdc-worker` — position confirmée par lecture du fichier réel avant
   édition, identique au texte du brief (profil `export`, build via
   `context: ./core` + `dockerfile: ../deploy/export-worker/Dockerfile`,
   env `DATABASE_URL`/`S3_*`/`CORE_EXPORT_ENABLED`/
   `CORE_EXPORT_TOKEN_SECRET`/`SHELL_BASE_URL`, `depends_on: [pgbouncer,
   minio]`).
6. **`.env.example`** : bloc `SHELL_BASE_URL` ajouté juste après
   `CORE_EXPORT_TOKEN_SECRET=`, avant le bloc
   `CORE_PIPELINES_EGRESS_ALLOWLIST`.

Vérification supplémentaire (non demandée explicitement mais faite par
prudence) : `grep` des noms de variables d'environnement
(`S3_EXPORTS_BUCKET`, `CORE_EXPORT_ENABLED`, `CORE_EXPORT_TOKEN_SECRET`,
`SHELL_BASE_URL`) contre le code réel (`app/export/jobs.py`,
`app/export/routes.py`, `app/auth/export_tokens.py`,
`app/auth/dependency.py`) — tous correspondent exactement à ce que le
service compose fournit.

## `lint-imports`

Une seule exécution nécessaire (aucune violation trouvée, donc pas de
"avant/après" à comparer) :

```
Analyzed 163 files, 490 dependencies.
-------------------------------------

layered architecture KEPT

Contracts: 1 kept, 0 broken.
```

Aucun import fautif d'une tâche précédente détecté — `app.export` respecte
le contrat de couches tel qu'inséré.

## `docker compose --profile export config -q`

Exit code 0. Sortie limitée à des warnings `"<VAR> variable is not set.
Defaulting to a blank string"` pour les variables d'environnement usuelles
non définies dans ce shell (pas de fichier `.env` chargé) — aucune erreur de
syntaxe ni de référence. Confirme que le service `export-worker` résout
correctement (image, profil, réseau, dépendances).

## Build Docker réel (Step 9)

**Résultat : succès complet**, pas seulement best-effort. Le démon Docker
était accessible (`docker info` OK) et l'accès réseau sortant a permis le
téléchargement complet de Chromium/FFmpeg/Chrome Headless Shell (~300 MiB
au total, via `playwright install --with-deps chromium`) :

```
docker compose --profile export build export-worker
...
#12 DONE 43.3s   (playwright install --with-deps chromium)
#17 exporting to image ... DONE 44.3s
 Image geostudio-export-worker Built
```

Aucune contrainte d'environnement rencontrée ici (contrairement au
précédent des tests `@pytest.mark.qgis` de SP-15d) — l'image `export-worker`
a été buildée pour de vrai, avec succès, dans cette session.

## Suite de tests complète (`core`)

```
cd core && uv run pytest -q
1317 passed, 137 skipped in 100.93s (0:01:40)
```

Aucune régression liée aux changements `jobs.py`/`pyproject.toml`. Les
skips sont les marqueurs habituels (`postgis`, `qgis`, `playwright` sans
binaire Chromium installé dans l'environnement de test `core` — le binaire
Chromium a été installé dans l'image Docker buildée, pas dans le venv `uv`
local qui a servi à `pytest`).

## Fichiers modifiés

- `core/app/jobs.py` (modifié) — `import_paths` +1 entrée.
- `core/pyproject.toml` (modifié) — `layers` +1 entrée, `ignore_imports` +1
  entrée.
- `deploy/export-worker/Dockerfile` (nouveau).
- `docker-compose.yml` (modifié) — +1 service `export-worker`.
- `.env.example` (modifié) — +1 bloc `SHELL_BASE_URL`.
- `core/tests/test_jobs.py` : **non modifié** (justification ci-dessus).

Note : `.superpowers/sdd/progress.md` apparaît modifié dans l'arbre de
travail (probablement par le processus orchestrateur en dehors de cette
tâche) — non touché par cette tâche, non inclus dans le commit
(`git add` explicite des 5 fichiers listés dans le brief uniquement).

## Auto-revue

- `import_paths` inclut `app.export.jobs` : confirmé (lecture du fichier
  après édition, plus test vert).
- `lint-imports` : 0 violation, `Contracts: 1 kept, 0 broken.`
- Dockerfile : contenu comparé ligne à ligne au brief — identique.
- Service compose : YAML valide (`docker compose config`), contenu comparé
  au brief — identique, position confirmée correcte (après `qgis-worker`,
  avant `cdc-worker`).
- `.env.example` documente `SHELL_BASE_URL` avec le commentaire du brief,
  à l'emplacement spécifié.
- Suite `core` complète verte (1317 passed, 137 skipped, 0 failed).
- Build Docker : succès réel observé, pas une simple affirmation.

## Concerns

Aucun. Toutes les étapes du brief ont été exécutées avec succès, y compris
le build Docker best-effort qui a en fait pleinement réussi. Aucune
violation import-linter à corriger (donc aucun fichier hors périmètre
touché). Le test `test_jobs.py` n'a pas eu besoin d'extension — décision
documentée ci-dessus, cohérente avec le fait que le même test n'a pas non
plus été étendu pour `app.pipelines.jobs`/`app.alerts.jobs` lors de leur
ajout.
