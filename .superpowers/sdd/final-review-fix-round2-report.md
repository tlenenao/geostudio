# SP-26 — revue finale, round 2 de correctifs (N1, N2, M1, M2, M4)

Contexte : la re-revue de la première passe de correctifs SP-26 a trouvé 6
des 7 constats réellement fermés (C1, I1-I5), plus I6 (runbook non-root)
seulement partiellement fermé, et 3 petits trous de qualité de test (Minor)
peu coûteux à fermer. Cette note documente cette seconde passe.

## N1 (Important) — commande `chown` de `backup-archives` non fonctionnelle

**Diagnostic confirmé empiriquement** (avant tout correctif) :

```
$ docker run --rm -v backup-archives-test:/v alpine chown -R backup:backup /v
chown: unknown user/group backup:backup
```

`alpine` générique n'a pas d'entrée `backup` dans `/etc/passwd`/`/etc/group`
(contrairement à Debian) — ce compte n'existe que dans l'image
`geostudio-backup` elle-même. De plus, le `backup` de
`deploy/backup/Dockerfile` était créé par `adduser -S` sans `--uid`
explicite : uid mesuré 100/gid 101 avant correctif, non stable d'un build à
l'autre.

**Correctif appliqué :**

1. `deploy/backup/Dockerfile` : `addgroup -g 1001 -S backup && adduser -S -G
   backup -u 1001 -h /home/backup backup` — uid/gid FIXÉS à 1001, même
   convention que C1 (`app`/`qgis`). Vérifié libre dans `alpine:3.20`
   (`getent passwd 1001`/`getent group 1001` → non trouvé, exit 2) avant
   de choisir ce nombre.
2. Runbook mis à jour : la commande documentée passe à un chown **numérique**
   (`chown -R 1001:1001`) plutôt qu'un chown par nom — un chown par uid
   numérique ne fait aucune résolution `/etc/passwd`, donc l'image `alpine`
   générique suffit sans avoir besoin de lancer `geostudio-backup` elle-même.
3. Vérification empirique complète (image reconstruite avec le pin) :
   - `docker run --rm --entrypoint id geostudio-backup:test2 backup` →
     `uid=1001(backup) gid=1001(backup)`.
   - Simulation d'un volume `backup-archives` root-owned issu d'un ancien
     déploiement (`touch`+`chown root:root` dans le volume).
   - Commande d'origine (`alpine chown backup:backup`) reproduite en échec :
     `chown: unknown user/group backup:backup` (exit 1).
   - Commande documentée désormais (`alpine chown -R 1001:1001 /v`) : exit 0,
     `stat` confirme `1001:1001` sur le répertoire et le fichier préexistant.

**Fichiers touchés** : `deploy/backup/Dockerfile`,
`docs/runbooks/2026-08-27-migration-conteneurs-non-root.md`.

## N2 (Important) — troisième volume non couvert : `appexport-runtime`

`deploy/appexport-runtime-builder/Dockerfile` crée un utilisateur `builder`
non-root (`groupadd --system && useradd --system --gid builder
--create-home builder`, sans `--uid` explicite) dont le `CMD` écrit dans le
volume nommé `appexport-runtime` (`cp -r dist-export/* /export-runtime/`) —
partagé en lecture seule avec `worker`. Le runbook ne mentionnait pas ce
volume.

**Correctif appliqué :**

1. `deploy/appexport-runtime-builder/Dockerfile` : `groupadd --system --gid
   1001 builder && useradd --system --uid 1001 --gid builder --create-home
   builder` — uid/gid FIXÉS à 1001, même convention. Vérifié libre dans
   `node:20-slim` (`getent passwd 1001`/`getent group 1001` → non trouvé ;
   `node` y occupe déjà 1000, donc pas de collision).
2. Nouvelle entrée ajoutée au runbook pour `appexport-runtime`, même format
   que `backup-archives`/`etl-scratch`, avec une note expliquant que les
   trois volumes n'ont pas de contrainte de convergence d'uid entre eux
   (contrairement à `etl-scratch`, seul volume à double écrivain non-root) —
   1001 est un choix de cohérence documentaire, pas une nécessité
   fonctionnelle pour `backup-archives`/`appexport-runtime`.
3. Vérification empirique complète :
   - `docker build -t geostudio-appexport-runtime-builder:test -f
     deploy/appexport-runtime-builder/Dockerfile .` → succès (contexte =
     racine du dépôt, comme documenté par le Dockerfile lui-même).
   - `docker run --rm --entrypoint id ... builder` → `uid=1001(builder)
     gid=1001(builder)`.
   - Simulation d'un volume `appexport-runtime` root-owned préexistant :
     une écriture en tant que `builder` non-root échoue en `Permission
     denied` (`mkdir: cannot create directory '/v/sub': Permission
     denied`) — reproduit le mode d'échec exact que N2 décrit.
   - Commande documentée (`alpine chown -R 1001:1001 /v`) appliquée au
     volume : exit 0, `stat` confirme `1001:1001`.
   - Réessai de l'écriture en tant que `builder` non-root après le chown :
     succès (`mkdir`/écriture/lecture aboutissent).

**Fichiers touchés** : `deploy/appexport-runtime-builder/Dockerfile`,
`docs/runbooks/2026-08-27-migration-conteneurs-non-root.md`.

Toutes les images/volumes Docker créés pour ces vérifications (`:test`,
`:test2`, `backup-archives-test`, `appexport-runtime-test`) ont été
supprimés après usage.

## M1 (Minor) — le test I2 ne couvrait qu'une des deux formes de régression

`test_core_env_default_cannot_silently_satisfy_the_mock_mode_guard`
n'extrayait la valeur de `CORE_ENV` que via une regex ciblant
`${CORE_ENV:-défaut}` — un `CORE_ENV: development` codé en dur (littéral,
sans aucune substitution) dans `docker-compose.yml` aurait fait retourner
`None` à l'ancien extracteur, et `None != "development"` passait le test
silencieusement, alors que c'est exactement la régression que ce test existe
pour attraper.

**Correctif appliqué :** `_substitution_default` remplacée par
`_resolve_effective_value`, qui calcule la valeur **résolue** (celle que le
service `core` recevrait avec aucun `.env` fourni) — gère `${VAR}`,
`${VAR:-défaut}` ET une valeur littérale directe (repli : la chaîne brute
elle-même quand elle ne matche aucune substitution). Les deux assertions du
test (`auth_mode`/`env`) utilisent désormais ce résolveur.

**Preuve RED→GREEN** (édition temporaire, revert immédiat après, pas de
`git stash` — confirmé par `git diff --stat` vide après coup) :
- RED : `docker-compose.yml`'s `CORE_ENV: ${CORE_ENV:-}` remplacé
  temporairement par `CORE_ENV: development` (littéral) → le test échoue :
  `AssertionError: CORE_ENV résout à 'development' ... assert 'development'
  != 'development'`.
- Revert → GREEN : `uv run pytest tests/test_deployability.py -k
  mock_mode_guard` → 1 passed.

**Fichier touché** : `core/tests/test_deployability.py`.

## M2 (Minor) — le test C1 ne couvrait que `core/Dockerfile`

`test_core_dockerfile_creates_and_chowns_scratch_before_switching_user`
n'existait que pour `core/Dockerfile` ; `deploy/qgis-worker/Dockerfile`
porte le même mkdir+chown de `/scratch`, tout aussi structurant pour le
partage `etl-scratch`, sans aucune couverture de test sur sa présence
structurelle (seule la valeur de l'uid était testée par
`test_core_and_qgis_worker_pin_the_same_scratch_uid`).

**Correctif appliqué :** le test est généralisé en
`test_dockerfile_creates_and_chowns_scratch_before_switching_user`,
paramétré sur `(CORE_DOCKERFILE, "app")` et `(QGIS_DOCKERFILE, "qgis")` — la
logique de vérification est réutilisée telle quelle, aucune duplication.

**Preuve RED→GREEN** (édition temporaire de `deploy/qgis-worker/Dockerfile`,
revert immédiat, `git diff --stat` vide après coup) :
- RED : la ligne `RUN mkdir -p /scratch && chown -R qgis:qgis ...`
  remplacée temporairement par `RUN mkdir -p /opt/qgis-home /app` (sans
  `/scratch` ni chown) → `test_dockerfile_creates_and_chowns_scratch_...
  [qgis-worker]` échoue (`assert -1 != -1`), `[core]` reste vert.
- Revert → GREEN : les deux paramétrisations passent.

**Fichier touché** : `core/tests/test_deployability.py`.

## M4 (Minor) — cross-référence CSP manquante dans `shell/nginx.conf`

Le bloqueur #4 de la checklist CSP (4 points, avant bascule Report-Only →
enforcing) vit entièrement dans `docker-compose.prod.yml`, mais concerne
`shell/nginx.conf`'s `connect-src 'self'` (faux pour le compose de base, où
`shell`/`core` sont deux origines distinctes) — quelqu'un éditant
`shell/nginx.conf` directement sans jamais ouvrir `docker-compose.prod.yml`
ne le verrait pas.

**Correctif appliqué :** un commentaire d'une ligne ajouté juste avant la
directive `Content-Security-Policy-Report-Only` dans `shell/nginx.conf`,
renvoyant vers l'explication complète dans `docker-compose.prod.yml`
(pas de duplication de la liste des 4 points).

**Fichier touché** : `shell/nginx.conf`. Pas de test requis (commentaire
seul).

## Preuves de sortie finales

- `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:gis@localhost:5433/gis_test
  uv run pytest tests/test_deployability.py -v` → **35 passed** (contre 33
  avant cette passe — +2 : la paramétrisation `[core]`/`[qgis-worker]`
  remplace l'unique test C1 d'origine, net +1, et le test M1 reste un seul
  test renommé/renforcé — le delta exact vient du passage d'un test unique à
  deux cas paramétrés pour M2).
- `uv run pytest -q` (suite complète, PostGIS réel) → **1896 passed, 5
  skipped, 1 failed** — le seul échec est
  `test_features_rls.py::test_scope_preserves_original_sql_error`, confirmé
  pré-existant et sans rapport avec cette session (non investigué, conforme
  à la consigne).
- `git diff --stat` sur les fichiers temporairement modifiés pour les
  vérifications RED (`docker-compose.yml`,
  `deploy/qgis-worker/Dockerfile`) : vide après revert — aucune trace
  résiduelle des manipulations RED.
- Tous les artefacts Docker de vérification (images `:test`/`:test2`,
  volumes `*-test`) supprimés après usage.

## Auto-revue

- **N1/N2** : la commande documentée est désormais prouvée par exécution
  réelle dans le scénario exact qu'elle doit résoudre (volume root-owned
  préexistant → chown → écriture non-root réussie), pas seulement relue.
  Le choix du chown numérique (plutôt que `--user root --entrypoint sh
  geostudio-backup -c "chown ..."`, testé aussi et fonctionnel mais plus
  lourd à documenter/exécuter) est cohérent avec l'entrée `etl-scratch`
  déjà existante dans le même runbook — un seul style de commande dans tout
  le fichier.
- **M1** : le résolveur généralisé reste défensif — un cas non couvert
  (substitution partielle mélangée à du texte, ex.
  `"prefix-${CORE_ENV:-x}-suffix"`) retomberait sur le repli littéral
  (`re.fullmatch` échoue, la chaîne brute entière est retournée), ce qui est
  un comportement sûr par défaut (ne prétend jamais résoudre à une valeur
  qu'il n'a pas vraiment isolée) même si ce n'est pas la forme réellement
  utilisée dans ce dépôt.
- **M2** : la paramétrisation réutilise 100% de la logique de vérification
  d'origine (aucune duplication), seul le nom de la variable/l'id de
  paramétrisation change.
- **M4** : commentaire volontairement court (pas de duplication de la
  checklist complète), pointant vers la source de vérité existante.
- Écart explicitement non traité (hors périmètre demandé) : M3 (rate-limit
  harvest sur OPTIONS/HEAD) — non touché, conformément à la consigne « Do
  NOT touch ».
