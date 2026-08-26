# SP-26 — Fix pass sur la revue finale de branche (1 Critical + 6 Important)

Session du 2026-08-27. Corrige les 7 findings (C1, I1-I6) de la revue finale
d'intégration croisée de SP-26 « Durcissement avant v0.1 publique ». Les
Minor (~8) sont explicitement hors périmètre, non touchés.

## C1 (Critical) — `/scratch` ownership + uid mismatch

### Problème 1 : `/scratch` jamais créé/chowné dans `core/Dockerfile`

`docker-compose.yml` monte le volume nommé `etl-scratch:/scratch` sur le
service `worker` (`build: ./core`, même image non-root que `core`).
`core/app/pipelines/runtime.py` (`os.makedirs(scratch_dir, exist_ok=True)`,
où `scratch_dir` est un sous-répertoire de `/scratch`) et
`core/app/terrain3d/jobs.py` (`tempfile.mkdtemp(dir="/scratch", ...)`) y
écrivent au runtime. `/scratch` n'existait pas dans l'image `core` : au
premier démarrage, Docker crée le point de montage en `root:root`, et
l'utilisateur non-root `app` échoue en `PermissionError`.

**Fix** : `core/Dockerfile` crée et chowne `/scratch` avant `USER app`,
même patron que `deploy/qgis-worker/Dockerfile` (déjà correct pour son
propre `/scratch`) et `deploy/backup/Dockerfile` (`/backup/archives`).

### Problème 2 : uid mismatch entre `app` (core) et `qgis` (qgis-worker)

`core/app/pipelines/runtime.py` (process `worker`, utilisateur `app`) écrit
`in.gpkg` dans un sous-répertoire de scratch, puis appelle le sidecar
`qgis-worker` (utilisateur `qgis`) en HTTP, qui doit écrire `out.gpkg` dans
le MÊME répertoire. `core/Dockerfile` et `deploy/qgis-worker/Dockerfile`
créaient chacun leur utilisateur via `useradd --system` SANS uid explicite,
sur deux images de base différentes (Debian pour core, Ubuntu pour
qgis-worker) — aucune garantie de convergence sur le même nombre.

**Fix** : les deux Dockerfiles fixent désormais `app`/`qgis` au MÊME
uid/gid explicite, **1001**, choisi après vérification que ce nombre est
libre dans les deux images de base :

```
docker run --rm python:3.12-slim getent passwd 1001   # exit 2 (libre)
docker run --rm qgis/qgis:release-3_34 getent passwd 1001  # exit 2 (libre)
```

Aucun troisième consommateur de `/scratch` ou d'un volume similaire trouvé
(`grep -n "/scratch" docker-compose.yml docker-compose.prod.yml` → seulement
`worker` et `qgis-worker`, deux occurrences chacun — le montage et son
commentaire).

### Vérification empirique (build réel des deux images)

```
$ docker build -q -t geostudio-core-c1test -f core/Dockerfile core
$ docker build -q -t geostudio-qgis-worker-c1test -f deploy/qgis-worker/Dockerfile deploy/qgis-worker

$ docker run --rm geostudio-core-c1test id
uid=1001(app) gid=1001(app) groups=1001(app)
$ docker run --rm geostudio-qgis-worker-c1test id
uid=1001(qgis) gid=1001(qgis) groups=1001(qgis)
```

**RED (comportement pré-fix reproduit)** : Dockerfile minimal reproduisant
l'ancien `useradd --system` sans `/scratch` créé dans l'image, volume nommé
vierge monté :

```
$ docker run --rm -v scratch-red-test:/scratch c1red-core sh -c "ls -ld /scratch; touch /scratch/in.gpkg"
drwxr-xr-x 2 root root 4096 ... /scratch
touch: cannot touch '/scratch/in.gpkg': Permission denied
exit code: 1
```

**GREEN (image corrigée)** :

```
$ docker run --rm -v scratch-green-test:/scratch geostudio-core-c1test sh -c "ls -ld /scratch; touch /scratch/in.gpkg && echo WRITE_OK"
drwxr-xr-x 2 app app 4096 ... /scratch
WRITE_OK
```

**Écriture croisée réelle, les deux ordres de démarrage possibles** (le
volume nommé est seedé par la PREMIÈRE image qui le monte — l'ordre compte) :

- Scénario A (`worker`/core démarre en premier, écrit `in.gpkg`, puis
  `qgis-worker` mounte le même volume et écrit `out.gpkg` à côté) : succès,
  les deux fichiers présents, propriétaire numérique 1001 des deux côtés.
- Scénario B (ordre inverse, `qgis-worker` d'abord) : succès identique.

Les deux scénarios ont réellement été exécutés (deux `docker run`
successifs partageant un volume nommé réel, pas une simulation) — sortie
complète dans la transcription de session, `ls -la` confirmant les deux
fichiers présents et accessibles en écriture des deux côtés dans les deux
ordres.

Images/volumes de test nettoyés après vérification
(`docker rmi`/`docker volume rm`).

### Test statique de régression

`core/tests/test_deployability.py` :
- `test_core_and_qgis_worker_pin_the_same_scratch_uid` — épingle que les
  deux Dockerfiles déclarent le MÊME `--uid` numérique.
- `test_core_dockerfile_creates_and_chowns_scratch_before_switching_user` —
  épingle que `core/Dockerfile` crée+chowne `/scratch` avant `USER app`.

**Fichiers touchés** : `core/Dockerfile`, `deploy/qgis-worker/Dockerfile`,
`core/tests/test_deployability.py`.

## I1 (Important) — budget harvest tuait le sélecteur de couches externes

`_HARVEST_RE` couvrait TOUTES les routes `/harvest/*`, y compris
`GET /harvest/layers`/`GET /harvest/feature-layers` (lectures pures,
couches déjà enregistrées en base, aucun appel externe) que
`LayerPicker.tsx` interroge à chaque frappe sans debounce.

**Fix** : `route_group()` gagne un paramètre `method` ; le groupe `harvest`
n'est retenu que pour les routes `/harvest/*` dont la méthode n'est PAS
`GET` (les 4 routes à coût réel — create/patch/delete/run — sont toutes
POST/PATCH/DELETE ; les 4 routes de lecture — list_sources, list_layers,
list_feature_layers, get_source — sont toutes GET). Site d'appel unique
(`core/app/main.py`) mis à jour pour passer `request.method`.

**Tests** (`core/tests/test_ratelimit.py`) :
- `test_route_group_ignores_get_on_harvest_paths` (unitaire)
- `test_route_group_covers_harvest_writes` (unitaire)
- `test_harvest_read_routes_are_not_rate_limited` (HTTP, 15× GET sans 429)
- `test_harvest_write_routes_stay_rate_limited` (HTTP, 11× POST → au moins
  un 429)

Shell non touché (portée du fix limitée à la regex serveur, comme demandé).

**Fichiers touchés** : `core/app/ratelimit/limiter.py`, `core/app/main.py`,
`core/tests/test_ratelimit.py`.

## I2 (Important) — le défaut compose désarmait la garde mock-mode

`docker-compose.yml` câblait `CORE_AUTH_MODE: ${CORE_AUTH_MODE:-mock}` ET
`CORE_ENV: ${CORE_ENV:-development}` — quiconque démarre le fichier de base
sans `.env` obtient les deux par défaut, et
`reject_mock_outside_development()` (qui ne refuse `mock` que si
`CORE_ENV != "development"`) ne se déclenche jamais.

**Fix** : `CORE_ENV: ${CORE_ENV:-}` (défaut vide). Le flux documenté
(`.env.example` → `scripts/bootstrap-env.sh` → `.env`) fixe toujours
`CORE_ENV=development` explicitement et n'est pas affecté — vérifié :
`.env.example:30` porte `CORE_ENV=development` en ligne active.

**Test** (`core/tests/test_deployability.py`) :
`test_core_env_default_cannot_silently_satisfy_the_mock_mode_guard` — lit
la valeur brute de substitution `${CORE_ENV:-...}` du service `core` dans
`docker-compose.yml` et vérifie qu'elle n'est plus `"development"`.

**Re-runs demandés par le brief** :
- `tests/test_deployability.py` → 34/34 (31 existants + 1 nouveau I2 + 2
  nouveaux C1) — aucune régression sur le wiring existant.
- `tests/test_mock_mode_guard.py` → 3/3 verts, inchangé — ces tests testent
  le garde applicatif lui-même (`create_app()` + monkeypatch), indépendants
  du défaut compose ; rien n'y supposait ce défaut.

**Fichiers touchés** : `docker-compose.yml`, `core/tests/test_deployability.py`.

## I3 (Important) — 403 lecture-seule en JSON plat, pas RFC 7807

`read_only_guard` (middleware, `core/app/main.py`) renvoyait
`{"detail": "..."}` en `application/json` nu — forme antérieure à Task 3
(RFC 7807), jamais mise à jour car Task 3 portait sur les exception
handlers, pas ce middleware.

**Fix, inline (pas d'extraction de helper — choix conservateur demandé par
le brief)** : même forme que `_http_exception_handler`/le 429 du rate
limiter — `media_type="application/problem+json"`, corps
`{"type": "about:blank", "title": HTTPStatus(403).phrase, "status": 403,
"detail": "Mode démo : lecture seule, écritures désactivées."}`.

**Test** : `core/tests/test_read_only_mode.py`'s
`test_read_only_mode_blocks_every_mutation_even_for_admin` mis à jour
(TDD — RED confirmé en lisant l'ancienne assertion `{"detail": ...}` avant
modification, GREEN après le fix) : vérifie désormais
`content-type == "application/problem+json"` et le corps RFC 7807 complet
(`type`/`title`/`status`/`detail`). Les autres tests du même fichier qui
comparent au message `READ_ONLY_MESSAGE` par inégalité
(`test_analytics_sql_is_exempt_from_read_only`) restent corrects sans
changement. `test_mcp_read_only_mode.py` non affecté : `/mcp` est
explicitement exempté de ce middleware, son message provient d'un chemin
MCP distinct.

**Fichiers touchés** : `core/app/main.py`, `core/tests/test_read_only_mode.py`.

## I4 (Important) — `_hits` croît sans borne sous rotation de jeton OIDC

`RateLimiter._hits` était clé sur l'en-tête `Authorization` brut (un JWT
complet sous OIDC réel, qui tourne toutes les quelques minutes) et n'était
jamais purgé au niveau du dict — seule la deque de la clé COURANTE était
purgée à chaque appel ; une clé qui n'est plus jamais réutilisée après
rotation restait dans `_hits` pour toujours. Le docstring affirmait à tort
que cette croissance était « négligeable ».

**Fix** : balayage périodique (`_sweep`, toutes les `_SWEEP_INTERVAL=50`
requêtes, pas à chaque appel — coût O(n) borné plutôt que sur le chemin
chaud de chaque requête) qui purge TOUTES les deques du dict et retire les
entrées retombées à vide. Docstring corrigé : la limite réelle documentée
est maintenant « pas de partage inter-répliques » (C2/vague 0), plus la
fausse affirmation de croissance négligeable.

**Test** (`core/tests/test_ratelimit.py`) :
`test_expired_bucket_is_pruned_from_hits` — `time.monotonic` monkeypatché,
une clé `"stale-caller"` appelée une fois puis jamais réutilisée ; après
avance de temps > fenêtre + `_SWEEP_INTERVAL` appels d'une AUTRE clé,
vérifie `("stale-caller", "harvest") not in limiter._hits` (comparaison
d'appartenance au dict, pas juste un comportement observable équivalent).

**Fichiers touchés** : `core/app/ratelimit/limiter.py`,
`core/tests/test_ratelimit.py`.

## I5 (Important, documentation seule) — 4 bloqueurs CSP avant enforcing

Note ajoutée dans `docker-compose.prod.yml`, juste avant la ligne
`Content-Security-Policy-Report-Only` : les 4 points listés dans le brief
(img-src bloque WMS/WMTS+terrain externes ; connect-src bloque tileset 3D
externe ; script-src 'self' bloque les widgets d'extension tiers ;
`shell/nginx.conf`'s connect-src 'self' est spécifiquement faux pour le
compose de base hors overlay prod). Aucun changement de code.

**Fichiers touchés** : `docker-compose.prod.yml` (commentaire seul).

## I6 (Important, documentation seule) — volumes nommés existants cassés à l'upgrade

`docs/runbooks/` existe (un seul fichier, restauration de sauvegarde —
scénario différent : machine neuve, volumes vierges, pas d'upgrade en
place). Créé `docs/runbooks/2026-08-27-migration-conteneurs-non-root.md`
(même convention de nommage daté que le runbook existant) : explique
pourquoi un volume nommé déjà peuplé par d'anciennes images root reste
`root:root` après upgrade (Docker ne fixe la propriété qu'à la première
création du volume), et donne les commandes `docker run --rm -v <volume>:/v
alpine chown -R <uid>:<gid> /v` pour `backup-archives` (`backup:backup`) et
`etl-scratch` (`1001:1001`, les valeurs réelles choisies en C1).

**Fichiers touchés** : `docs/runbooks/2026-08-27-migration-conteneurs-non-root.md`
(nouveau).

## Preuves de sortie finales (2026-08-27)

- `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:gis@localhost:5433/gis_test uv run pytest -q`
  → **1895 passed, 5 skipped, 1 failed** (225.57s). L'échec est
  `tests/test_features_rls.py::test_scope_preserves_original_sql_error` —
  confirmé pré-existant et sans rapport avec cette branche (assertion sur le
  message d'erreur SQL exact remonté par psycopg2 lors d'un `RESET ROLE`
  après transaction avortée ; ne touche aucun fichier modifié par ce fix
  pass). Dépasse le plancher attendu (1887+).
- `uv run ruff check .` → All checks passed!
- `uv run ruff format --check .` → 503 files already formatted
- `uv run mypy --strict app/auth app/secrets app/analytics app/copilot` →
  Success: no issues found in 21 source files
- `uv run lint-imports` → Contracts: 1 kept, 0 broken.
- `uv run pytest tests/test_deployability.py -q` → **34 passed** (31
  d'origine + 3 nouveaux : I2 + 2×C1).

## Auto-revue contre chaque finding

- **C1** : fermé — `/scratch` créé+chowné dans `core/Dockerfile` ; uid/gid
  1001 identiques et VÉRIFIÉS libres dans les deux images de base ; écriture
  croisée réelle prouvée dans les DEUX ordres de démarrage (pas seulement
  uid égal — le brief demandait explicitement de ne pas s'arrêter à
  l'égalité des uid) ; aucun troisième consommateur de `/scratch`.
- **I1** : fermé — seules les 4 routes à coût réel restent limitées ; shell
  non touché comme demandé.
- **I2** : fermé — défaut compose neutralisé, flux `.env.example` non
  affecté, testé.
- **I3** : fermé — forme RFC 7807 alignée sur les 3 autres sites existants,
  fix inline conservateur (pas d'extraction de helper, comme suggéré en
  option la plus sûre par le brief).
- **I4** : fermé — croissance bornée par balayage périodique de TOUT le
  dict (pas seulement la clé courante), docstring corrigé, test prouvant le
  retrait effectif (pas juste l'absence de croissance immédiate).
- **I5** : fermé — note concise (9 lignes utiles) au bon endroit, 4 points
  du brief tous couverts, aucun code touché.
- **I6** : fermé — runbook dédié créé (aucun autre document ne convenait
  mieux), commandes concrètes avec les vraies valeurs uid/gid de C1.

Minor du brief : non touchés, comme demandé explicitement (« Do NOT fix »).
