# Task 3 report — `GEOSTUDIO_PUBLIC_HOST` source de vérité unique (SP-Deploy-a)

*(Ce fichier contenait auparavant un rapport d'une tâche "Task 3" différente
d'une session antérieure — SP-12g, connecteur CKAN. Écrasé en totalité avec
le rapport de la tâche actuelle.)*

## Ce qui a été implémenté

`docker-compose.prod.yml` modifié selon les Steps 1-4 du brief, transcrits
verbatim (labels, environment, entrypoint, command) **sauf** :

1. **Correction autorisée** : partout où le brief écrit `ports: []`
   (`keycloak`, `martin`), écrit `ports: !reset []` — cohérent avec le
   correctif déjà appliqué en Task 2 pour `minio`/`titiler`/`core`/`shell`/
   `traefik` (Compose concatène les champs liste-de-mapping `ports:`/
   `volumes:` entre fichiers `-f` au lieu de remplacer).

2. **Une correction supplémentaire, non prévue par le brief, appliquée**
   (bug équivalent trouvé en validant le merge réel — voir ci-dessous), et
   **une seconde, signalée mais non corrigée**.

Blocs remplacés/ajoutés : `keycloak:` (Step 1), `martin:` (Step 2, nouveau
bloc `labels:`), `core:` (Step 3), `shell:` (Step 4). Rien d'autre modifié
(pas de `tunnel:` — Task 5 ; pas de mécanisme runtime shell — Task 4).

## Découverte critique et corrigée : collision de volumes sur `keycloak`

En résolvant `docker compose config`, j'ai constaté que le service
`keycloak` du **`docker-compose.yml` de base** définit déjà :
```yaml
volumes:
  - keycloak-data:/opt/keycloak/data
  - ./deploy/keycloak/geostudio-realm.json:/opt/keycloak/data/import/geostudio-realm.json:ro
```
Le brief Step 1 ajoute un troisième volume (`.../import-src/...:ro`) sans
`!reset`/`!override`. Comme `volumes:` est concaténé entre fichiers (même
mécanisme documenté pour `ports:` dans le contexte de cette tâche), le
résultat fusionné contenait **les trois entrées** — y compris le bind-mount
`:ro` hérité du dev directement sur `/opt/keycloak/data/import/
geostudio-realm.json`.

C'est fatal : l'entrypoint prod fait
`sed ... > /opt/keycloak/data/import/geostudio-realm.json`, une redirection
d'écriture sur un chemin qui reste bind-monté en lecture seule depuis la
base — le conteneur aurait crashé au démarrage ("Read-only file system").

**Correctif appliqué** : `volumes: !override` sur le bloc `keycloak`, avec
la liste complète voulue (volume nommé `keycloak-data` + bind `:ro` vers
`import-src/`). Vérifié séparément : `!reset` suivi d'une liste non vide
**vide totalement le champ** (testé en isolation dans un mini compose-file —
piège de la balise, comportement inattendu) ; `!override` remplace bien par
le contenu donné, sans concaténation ni vidage. Après correctif, le
`docker compose config` résolu montre exactement 2 volumes pour `keycloak`,
plus de collision sur `import/`.

J'ai jugé ce correctif dans le périmètre autorisé (bien que le brief liste
`volumes` parmi les champs à "transcrire exactement") car : (a) il relève du
même mécanisme de fusion explicitement nommé dans le contexte de cette
tâche ; (b) sans lui, le script d'entrypoint **tel qu'écrit dans le brief
lui-même** ne peut pas s'exécuter — le corriger sert l'intention du brief,
pas une refonte.

## Trouvé mais NON corrigé (signalé pour décision) : labels résiduels `tls.certresolver`

Le `core:` et le `shell:` de base ont des `labels:` Traefik incluant
`traefik.http.routers.{core,shell}.tls.certresolver=letsencrypt` et
`entrypoints=websecure`. Le brief Step 3/4 les remplace par une nouvelle
liste (`entrypoints=web`, pas de `tls.certresolver`) en affirmant que
`labels:` étant "liste-type", le remplacement serait complet.

Vérifié faux : Compose normalise `labels:` en **mapping** et fusionne
**par clé** (comme `environment:`) plutôt que par concaténation ou
remplacement de liste. Résultat : dans le `docker compose config` résolu,
`core` et `shell` portent toujours
`traefik.http.routers.{core,shell}.tls.certresolver: letsencrypt`, hérité
de la base, alors que le brief voulait explicitement ce retrait ("retirés").

Impact potentiel : le `command:` Traefik prod ne déclare aucun
`--certificatesresolvers.letsencrypt...` ni d'entrypoint `websecure` — cette
clé référence donc un resolver inexistant. Selon la version de Traefik,
cela peut aller d'un simple warning ignoré à un routeur invalide/non
chargé (risque non vérifié ici — je n'ai pas démarré la stack réelle, pas
de conteneurs lancés, uniquement `docker compose config`).

**Je n'ai pas corrigé ce point** : contrairement au cas `volumes`
(mécanisme explicitement nommé dans le contexte + casse garantie et
immédiate), celui-ci est un mécanisme différent (fusion de mapping, pas de
concaténation de liste), d'impact incertain, et `labels` est explicitement
listé dans la consigne "transcrit exactement" — j'ai jugé que trancher
unilatéralement ici sortait de mon mandat. Remède suggéré si confirmé
nécessaire : `labels: !override` avec la liste complète (même pattern que
le correctif `volumes` ci-dessus), sur les blocs `core:` et `shell:`
uniquement (martin/keycloak n'ont pas de labels de base, donc pas de fuite
possible chez eux).

## Validation effectuée

- `.env` existant (57 lignes) **non touché** — utilisé
  `GEOSTUDIO_PUBLIC_HOST=test.ts.net GEOSTUDIO_VERSION=... docker compose
  -f docker-compose.yml -f docker-compose.prod.yml config` avec variables
  passées inline plutôt que d'écrire dans `.env`.
- `docker compose config` : exit 0, YAML valide.
- Les trois interpolations demandées, confirmées dans le config résolu :
  - `CORE_OIDC_ISSUER: https://test.ts.net/auth/realms/geostudio`
  - `KC_HOSTNAME: https://test.ts.net`
  - `VITE_CORE_URL: https://test.ts.net/api`
  - (bonus vérifié aussi : `VITE_MARTIN_URL`, `VITE_OIDC_AUTHORITY`,
    `VITE_OIDC_REDIRECT_URI`, `CORE_OIDC_JWKS_URL` — tous corrects, aucun
    littéral `${GEOSTUDIO_PUBLIC_HOST}` restant)
- **Ports vides confirmés par parsing YAML réel** (pas juste "exit 0") :
  script Python chargeant le YAML résolu et vérifiant l'absence de clé
  `ports` (donc vide) pour `keycloak`, `martin`, `core`, `shell` — les
  quatre confirmés.
- **Volumes `keycloak` vérifiés après correctif** : exactement 2 entrées
  (`keycloak-data:/opt/keycloak/data`, bind `:ro` vers `import-src/`), plus
  de collision sur `import/`.

## Fichiers modifiés

- `/home/lenen/projets/geostudio/docker-compose.prod.yml` (seul fichier
  modifié, comme demandé)

## Auto-revue (checklist de la mission)

- Complétude : les 4 blocs (`keycloak`, `martin`, `core`, `shell`) suivent
  le brief, correctif `!reset` appliqué partout où `ports: []` apparaissait.
- Qualité : deux bugs de fusion Compose non anticipés par le brief détectés
  par vérification réelle du merge (pas seulement syntaxe) — un corrigé
  (volumes/keycloak, cassait le démarrage), un signalé sans correction
  (labels/tls.certresolver, impact incertain, hors mandat explicite).
- Discipline de périmètre : pas de bloc `tunnel:` (Task 5), pas de mécanisme
  runtime shell (Task 4) — uniquement Steps 1-4 + validation.
- `docker compose config` confirmé : ports vides pour les 4 services par
  parsing YAML réel, pas seulement `exit 0`.

## Préoccupations pour la suite

1. **À trancher avant mise en prod réelle** : le résidu
   `tls.certresolver=letsencrypt` sur `core`/`shell` (voir section
   ci-dessus). Recommandation : `labels: !override` avec liste complète,
   à valider en Task 6 (validation end-to-end) ou en patch immédiat.
2. Le correctif `volumes: !override` sur `keycloak` change une ligne que le
   brief demandait de transcrire à l'identique — documenté en détail
   ci-dessus avec preuve reproductible, à valider par le contrôleur.
3. Confirmé que `!reset` suivi d'une valeur non vide vide silencieusement
   tout le champ (testé isolément) — piège potentiel pour Task 4/5/6 si
   elles réutilisent `!reset` avec du contenu ; `!override` est le bon tag
   pour "remplacer par cette liste".
4. Les fichiers `.superpowers/sdd/task-1-brief.md`, `task-1-report.md`,
   `task-2-brief.md`, `task-2-report.md`, `progress.md` apparaissent modifiés
   dans `git status` — ce n'est pas moi (je n'ai touché qu'à
   `docker-compose.prod.yml`) ; probablement la bookkeeping de
   l'orchestrateur en parallèle. Signalé pour éviter toute confusion au
   moment du commit/revue.

## Commit

`868dc66` — `feat(deploy): GEOSTUDIO_PUBLIC_HOST — source de vérité unique
(Keycloak, cœur, shell, Martin, Traefik)` (1 fichier, +63/-0, sur
`docker-compose.prod.yml` uniquement).

---

## Addendum — correctif du résidu `tls.certresolver` (revue de contrôleur)

Le point signalé mais non corrigé ci-dessus ("Trouvé mais NON corrigé :
labels résiduels `tls.certresolver`") a été confirmé par le contrôleur et
corrigé dans un commit séparé.

### Ce qui a changé

Dans `docker-compose.prod.yml`, les blocs `core:` et `shell:` : la clé
`labels:` devient `labels: !override` (contenu des listes inchangé, aucune
ligne de label modifiée). `keycloak:` et `martin:` n'ont pas été touchés
(la base `docker-compose.yml` ne définit `labels:` pour aucun des deux —
confirmé par `grep -n "labels:" docker-compose.yml`, qui ne pointe que sur
les blocs `core`/`shell` — donc pas de fusion, pas de fuite possible).

### Vérification exécutée

```bash
cd /home/lenen/projets/geostudio
GEOSTUDIO_PUBLIC_HOST=test.ts.net GEOSTUDIO_VERSION=latest TS_AUTHKEY= docker compose -f docker-compose.yml -f docker-compose.prod.yml config | python3 -c "
import sys, yaml
d = yaml.safe_load(sys.stdin)
for svc in ['core','shell']:
    labels = d['services'][svc]['labels']
    print(svc, 'tls.certresolver =', labels.get(f'traefik.http.routers.{svc}.tls.certresolver'))
"
```
Sortie après correctif :
```
core tls.certresolver = None
shell tls.certresolver = None
```

Sanity check complet :
```bash
GEOSTUDIO_PUBLIC_HOST=test.ts.net GEOSTUDIO_VERSION=latest TS_AUTHKEY= docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo OK
```
→ `OK`

Ré-vérification que l'interpolation d'URL n'a pas régressé (même host de
test, mêmes trois variables citées dans le rapport initial) :
```
CORE_OIDC_ISSUER = https://test.ts.net/auth/realms/geostudio
KC_HOSTNAME = https://test.ts.net
VITE_CORE_URL = https://test.ts.net/api
```
Identique à avant le correctif — confirmé que le changement est localisé
aux labels Traefik uniquement.

### Diff appliqué

```diff
-    labels:
+    labels: !override
       - traefik.enable=true
       - traefik.http.routers.core.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/api`)
...
-    labels:
+    labels: !override
       - traefik.enable=true
       - traefik.http.routers.shell.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`)
```
(2 lignes changées, 1 fichier — `docker-compose.prod.yml`.)

### Commit

`a6fe9ef` — `fix(deploy): labels fusionnent par clé — tls.certresolver
résiduel sur core/shell (revue Task 3)` (commit séparé, ne modifie pas
`868dc66`).

### Concern de la Task 3 initiale ainsi résolu

La "Préoccupation pour la suite" #1 ci-dessus ("À trancher avant mise en
prod réelle") est levée par ce correctif. Les deux autres préoccupations
(le correctif `volumes: !override` sur `keycloak`, et le piège `!reset` +
valeur non vide) restent valables et non affectées par ce changement.

---

## Correctif Task 6 — healthcheck Keycloak sondait le mauvais chemin

Défaut trouvé lors de la validation end-to-end (Task 6), attribuable à la
Task 3 : le bloc `keycloak:` de `docker-compose.prod.yml` fixe
`KC_HTTP_RELATIVE_PATH: /auth`, ce qui déplace toute la surface HTTP de
Keycloak (y compris son endpoint de santé) sous `/auth`. Mais ce bloc
n'écrase jamais le `healthcheck:` hérité du `docker-compose.yml` de base
(lignes 256-261), qui sonde en dur `GET /health/ready` à la racine. Task 6 a
confirmé empiriquement sur la stack réelle : `GET /health/ready` → `404`,
`GET /auth/health/ready` → `200 OK` avec `{"status": "UP", "checks": []}` —
Keycloak fonctionne, mais Docker le rapporte `unhealthy` en permanence.

### Ce qui a changé

Ajout d'un `healthcheck:` dans le bloc `keycloak:` de
`docker-compose.prod.yml`, même forme/timing que la base (`interval: 10s`,
`timeout: 5s`, `retries: 10`, `start_period: 30s`), seul le chemin dans la
commande `test:` change (`/health/ready` → `/auth/health/ready`), même
technique HTTP brut sur `/dev/tcp` (l'image n'a ni `curl` ni `wget`) :

```yaml
    healthcheck:
      test: ["CMD-SHELL", "exec 3<>/dev/tcp/localhost/8080 && echo -e 'GET /auth/health/ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && grep -q 'UP' <&3"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
```

### Vérification exécutée

Aucun `.env` n'existait au départ dans le dépôt. Généré un `.env` scratch via
`./scripts/bootstrap-env.sh` pour la durée de la vérification, supprimé
ensuite.

Premier essai avec le projet Compose par défaut (`postgis`+`keycloak`) :
Keycloak crashloopait avec `FATAL: password authentication failed for user
"gis"`. Cause : le volume Docker préexistant `geostudio_pg-data` (issu d'une
session antérieure, cf. "Suivis non bloquants ouverts" du CLAUDE.md — volume
déjà signalé comme cassé) contenait un rôle Postgres `gis` avec un mot de
passe différent de celui du nouveau `.env` scratch — Postgres n'exécute ses
scripts d'init (dont la définition du mot de passe) que sur un data dir
vide. Rien à voir avec le correctif healthcheck ; contourné en isolant la
vérification sous un nom de projet Compose distinct (`-p gs-verify`), qui
crée ses propres volumes neufs sans toucher au volume `geostudio_pg-data`
préexistant.

```bash
cd /home/lenen/projets/geostudio
[ -f .env ] || ./scripts/bootstrap-env.sh   # .env n'existait pas → généré

GEOSTUDIO_PUBLIC_HOST=test.ts.net GEOSTUDIO_VERSION=latest TS_AUTHKEY= \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml -p gs-verify \
  up -d postgis keycloak

# poll jusqu'à résolution du healthcheck (start_period 30s + retries)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -p gs-verify ps keycloak
```

Sortie confirmant `healthy` :
```
NAME                   IMAGE                            COMMAND                  SERVICE    CREATED          STATUS                    PORTS
gs-verify-keycloak-1   quay.io/keycloak/keycloak:24.0   "sh -c 'mkdir -p /op…"   keycloak   58 seconds ago   Up 46 seconds (healthy)   8080/tcp, 8443/tcp
```

```bash
docker inspect gs-verify-keycloak-1 --format='{{.State.Health.Status}}'
# → healthy

docker exec gs-verify-keycloak-1 sh -c "exec 3<>/dev/tcp/localhost/8080 && echo -e 'GET /auth/health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3 && cat <&3"
```
Sortie :
```
HTTP/1.1 200 OK
content-type: application/json; charset=UTF-8
connection: close
content-length: 45

{
    "status": "UP",
    "checks": [
    ]
}
```

### Nettoyage

```bash
GEOSTUDIO_PUBLIC_HOST=test.ts.net GEOSTUDIO_VERSION=latest TS_AUTHKEY= \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml -p gs-verify down -v
rm -f .env
docker rmi gs-verify-postgis:latest
```
- Conteneurs `gs-verify-postgis-1`/`gs-verify-keycloak-1` : arrêtés et
  supprimés (`down -v`, y compris leurs volumes/réseau dédiés
  `gs-verify_*`).
- `.env` scratch : supprimé (confirmé `ls .env` → absent, comme avant la
  vérification).
- Volumes préexistants `geostudio_pg-data`, `geostudio_keycloak-data`,
  `geostudio_minio-data` : non touchés (confirmé par `docker volume ls`
  après nettoyage — toujours présents, inchangés).
- Image scratch `gs-verify-postgis:latest` (buildée par le premier essai
  avec le projet par défaut, puis reconstruite sous `gs-verify`) :
  supprimée.
- Essai initial (projet Compose par défaut, avant l'isolation `-p
  gs-verify`) : conteneurs `geostudio-postgis-1`/`geostudio-keycloak-1`
  arrêtés et supprimés (`down`, sans `-v` — le volume `geostudio_pg-data`
  préexistant préservé intentionnellement, non détruit).

### Fichier modifié

- `/home/lenen/projets/geostudio/docker-compose.prod.yml` (seul fichier
  modifié — ajout du bloc `healthcheck:` dans `keycloak:`).

### Commit

`fix(deploy): healthcheck Keycloak sous le préfixe /auth (défaut trouvé en
Task 6)` — commit séparé, ne modifie ni `868dc66` ni `a6fe9ef`.
