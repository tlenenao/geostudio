# SP-21 « Déployabilité » — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** rendre déployable en production tout ce qui est déjà livré (export PDF, rapports planifiés, QGIS, export d'apps, sauvegarde), et installer le garde-fou automatique qui empêche la classe de bug « capacité livrée, non câblée » de revenir une 5ᵉ fois.

**Architecture:** un seul fichier de tests nouveau, `core/tests/test_deployability.py`, qui lit `docker-compose.yml`, `docker-compose.prod.yml`, `.github/workflows/release.yml`, `.env.example`, `deploy/backup/backup.sh` et l'arbre `core/app/`, et impose 7 règles. Chaque tâche écrit une règle (rouge), puis corrige le dépôt jusqu'au vert. Aucune tâche ne laisse l'arbre rouge. Aucun code applicatif n'est touché, sauf un script de sonde nouveau (`core/scripts/healthcheck_cdc.py`).

**Tech Stack:** Python 3.12 / pytest / PyYAML (lecture des YAML), docker compose v2 (vérifications manuelles ponctuelles), GitHub Actions.

**Spec de référence :** `docs/superpowers/specs/2026-08-20-sp21-deployabilite-design.md`.

## Global Constraints

- Docs, commentaires et messages utilisateur en **français** ; identifiants et code en anglais.
- Commits **conventional**, petits, un sujet (`test(deploy):`, `ci(release):`, `fix(compose):`, `docs(ops):`).
- **Aucune modification de `core/app/`** hors le nouveau `core/scripts/healthcheck_cdc.py` : pas de changement de schéma REST, donc **aucune régénération OpenAPI/TS** attendue (un diff non vide sur `shell/src/api/generated/core-schema.d.ts` est le signe qu'une tâche est sortie du périmètre).
- **Aucune capacité ne doit s'allumer** par effet de bord : toute variable ajoutée au compose porte un défaut identique au défaut applicatif (`${VAR:-}` ou `${CORE_ETL_ENABLED:-false}`), et tous les profils compose existants (`export`, `etl`, `appexport`, `observability`) sont conservés à l'identique.
- **Les tags d'images sont résolus contre le registre, jamais devinés.** Les quatre valeurs de la tâche 5 ont été résolues le 2026-08-20 (commandes et sorties dans la tâche) ; si une commande de vérification les contredit, c'est la sortie de la commande qui gagne.
- Le fichier de tests n'utilise **jamais** docker. Les deux vérifications qui exigent docker sont des étapes manuelles explicites, dont la sortie est consignée dans le rapport de tâche.
- Suite de référence avant de commencer : `cd core && uv run pytest` → **1615 passed, 153 skipped** (mesuré le 2026-08-20). Toute tâche qui fait baisser ce nombre a cassé quelque chose.

## Écart assumé avec la spec

La spec (§5) ordonnait « écrire les 6 tests en entier, constater 5 rouges, puis corriger ». Ce plan **entrelace** : une tâche = une règle + son correctif, donc l'arbre et la CI sont verts à la fin de chaque tâche. Motif : une tâche qui laisse la CI rouge n'est pas revuable indépendamment, et une revue par tâche est le principal filet de ce dépôt. Le bénéfice recherché par la spec (le test définit le correctif, pas l'inverse) est conservé **à l'intérieur** de chaque tâche : le test s'écrit et échoue d'abord.

Deuxième écart : le plan ajoute une **7ᵉ règle** (`test_every_referenced_ghcr_image_is_released`), absente de la spec. Raison : dès que la tâche 2 remplace `build:` par `image:` dans l'overlay, la règle 1 (« tout `build:` a une image publiée ») ne contrôle plus rien pour ces services — plus aucun `build:` à contrôler. La règle 7 ferme la boucle dans l'autre sens : toute image `ghcr.io/tlenenao/geostudio-*` référencée par un compose doit être publiée par `release.yml`.

## File Structure

| Fichier | Rôle | Tâches |
|---|---|---|
| `core/tests/test_deployability.py` | **créé** — les 7 règles + les helpers de lecture (chargeur YAML tolérant aux tags Compose, extraction des `os.environ`, des substitutions, des buckets, des images) | 1→5 |
| `core/pyproject.toml` | **modifié** — `pyyaml` déclaré en dépendance `dev` (aujourd'hui transitive) | 1 |
| `.github/workflows/release.yml` | **modifié** — matrice `build-and-push` : 4 → 8 images | 1 |
| `docker-compose.prod.yml` | **modifié** — `image:` pour `export-worker`, `qgis-worker`, `appexport-runtime-builder`, `backup` ; pin `tailscale` | 2, 5 |
| `docker-compose.yml` | **modifié** — 6 variables câblées, 2 buckets sur `backup`, pins `minio`/`traefik`/`keycloak`, healthchecks, `depends_on` | 3→7 |
| `.env.example` | **modifié** — 5 variables non documentées, 3 buckets en commentaire | 3, 4 |
| `deploy/backup/backup.sh` | **modifié** — 3 → 5 buckets miroités, exclusions écrites | 4 |
| `docs/runbooks/2026-07-24-restauration-sauvegardes.md` | **modifié** — périmètre de sauvegarde explicite | 4 |
| `core/scripts/healthcheck_cdc.py` | **créé** — sonde du worker CDC (slot de réplication actif) | 6 |
| `core/tests/test_healthcheck_cdc.py` | **créé** — test unitaire de la sonde | 6 |
| `deploy/qgis-worker/Dockerfile`, `deploy/qgis-worker/LICENSE-QGIS.md` | **modifié/créé** — notice GPL dans l'image publiée | 8 |
| `docs/ops/redistribution-images.md` | **créé** — note de redistribution GPL | 8 |
| `CLAUDE.md` | **modifié** — clôture SP-21 | 9 |

---

### Task 1: Socle du garde-fou et images publiées (chantier 1.1)

**Files:**
- Create: `core/tests/test_deployability.py`
- Modify: `core/pyproject.toml` (groupe `dev`)
- Modify: `.github/workflows/release.yml` (matrice `build-and-push`)

**Interfaces:**
- Produces (utilisés par les tâches 2→5) : `REPO`, `BASE`, `PROD`, `RELEASE`, `ENV_EXAMPLE`, `BACKUP_SH`, `CORE_APP` (chemins `pathlib.Path`) ; `load_yaml(path) -> dict` ; `services(path) -> dict[str, dict]` ; `build_target(service) -> tuple[str, str] | None` ; `release_matrix() -> list[dict]`.
- Consumes: rien.

- [ ] **Step 1: Écrire le fichier de tests avec ses helpers et les deux règles d'images**

Créer `core/tests/test_deployability.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde-fou de déployabilité (SP-21, vague 1 du plan d'action 2026-08-20).

Ces tests ne testent pas `core/app/` : ils testent le **dépôt** —
`docker-compose.yml`, l'overlay de production, `release.yml`, `.env.example`
et `deploy/backup/backup.sh`. Entorse assumée au découpage : `core/` est le
seul répertoire du dépôt qui possède déjà un runner Python et une place dans
la CI (`uv run pytest` du job `core`), et la propriété vérifiée ici —
« toute capacité livrée est déployable » — n'a pas d'autre foyer.

Raison d'être : quatre capacités livrées, testées et mergées se sont révélées
non câblées dans la stack packagée (SP-17a, SP-17b, tileset3d, et
`CORE_ETL_ENABLED` trouvée en écrivant ces tests). Chaque règle ci-dessous
correspond à une de ces découvertes, et échoue sur le dépôt tel qu'il était
avant SP-21.
"""
import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "docker-compose.yml"
PROD = REPO / "docker-compose.prod.yml"
RELEASE = REPO / ".github/workflows/release.yml"
ENV_EXAMPLE = REPO / ".env.example"
BACKUP_SH = REPO / "deploy/backup/backup.sh"
CORE_APP = REPO / "core/app"

# Préfixe des images que nous publions nous-mêmes.
OWN_IMAGE_RE = re.compile(r"ghcr\.io/[^/]+/(geostudio-[a-z0-9-]+)")


class ComposeLoader(yaml.SafeLoader):
    """`docker-compose.prod.yml` utilise les tags de fusion propres à Compose
    (`ports: !reset []`) — `yaml.safe_load` lève un ConstructorError dessus.
    Ces tags disent *comment* fusionner, pas *quoi* : on les résout à leur
    valeur nue, aucune règle d'ici n'en dépend."""


def _drop_tag(loader, suffix, node):
    if isinstance(node, yaml.nodes.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.nodes.MappingNode):
        return loader.construct_mapping(node)
    return node.value


ComposeLoader.add_multi_constructor("!", _drop_tag)


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(), Loader=ComposeLoader) or {}


def services(path: pathlib.Path) -> dict:
    return load_yaml(path).get("services") or {}


def build_target(service: dict) -> tuple[str, str] | None:
    """(contexte, dockerfile) normalisé, ou None si le service n'a pas de
    `build:`. La forme courte (`build: ./core`) et la forme longue
    (`build: {context, dockerfile}`) donnent le même couple."""
    build = service.get("build")
    if build is None:
        return None
    if isinstance(build, str):
        return (build, "Dockerfile")
    return (build.get("context", "."), build.get("dockerfile", "Dockerfile"))


def release_matrix() -> list[dict]:
    return load_yaml(RELEASE)["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]


def test_every_build_service_has_a_released_image():
    """Tout service construit depuis les sources doit avoir une image
    publiée par la CI de release. Sinon, déployer la capacité exige de
    cloner le dépôt sur l'hôte de production et d'y compiler Chromium ou
    QGIS — ce que l'en-tête de l'overlay prod prétend justement éviter."""
    published = {(e["context"], e["dockerfile"]) for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            target = build_target(service)
            if target and target not in published:
                missing[f"{path.name}:{name}"] = target
    assert not missing, (
        "services construits depuis les sources sans image publiée dans "
        f"release.yml : {missing}. Ajouter une entrée à la matrice "
        "build-and-push avec exactement ce couple (context, dockerfile)."
    )


def test_every_referenced_ghcr_image_is_released():
    """Miroir de la règle précédente, dans l'autre sens : un service qui
    référence une de nos images GHCR doit la trouver publiée. Sans cette
    règle, remplacer un `build:` par un `image:` (tâche 2) supprimerait le
    contrôle au lieu de le satisfaire."""
    published = {e["image"] for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            match = OWN_IMAGE_RE.match(service.get("image") or "")
            if match and match.group(1) not in published:
                missing[f"{path.name}:{name}"] = match.group(1)
    assert not missing, (
        f"images GHCR référencées mais jamais publiées : {missing}."
    )
```

- [ ] **Step 2: Lancer les deux tests et vérifier qu'ils échouent pour la bonne raison**

```bash
cd core && uv run pytest tests/test_deployability.py -v
```

Attendu : `test_every_build_service_has_a_released_image` **FAILED** avec les 4 services attendus dans le message —
`docker-compose.yml:appexport-runtime-builder` → `('.', 'deploy/appexport-runtime-builder/Dockerfile')`,
`docker-compose.yml:qgis-worker` → `('./deploy/qgis-worker', 'Dockerfile')`,
`docker-compose.yml:export-worker` → `('./core', '../deploy/export-worker/Dockerfile')`,
`docker-compose.prod.yml:backup` → `('./deploy/backup', 'Dockerfile')`.
`test_every_referenced_ghcr_image_is_released` **PASSED** (vrai aujourd'hui, il garde la tâche 2).

Si le test échoue avec `ConstructorError: could not determine a constructor for the tag '!reset'`, le `ComposeLoader` est mal câblé — c'est le piège de cet overlay, corriger avant d'avancer.

- [ ] **Step 3: Déclarer PyYAML en dépendance de test**

Dans `core/pyproject.toml`, groupe `dev`, ajouter :

```toml
    "pyyaml>=6.0",  # SP-21 : tests/test_deployability.py lit les docker-compose*.yml
                    # et release.yml. Présent en transitif jusqu'ici — un import
                    # direct d'une dépendance non déclarée casse au premier
                    # changement d'arbre (même dette que le `anyio` de SP-20).
```

Puis :

```bash
cd core && uv sync
```

- [ ] **Step 4: Ajouter les 4 images à la matrice de release**

Dans `.github/workflows/release.yml`, à la fin de `strategy.matrix.include`, après l'entrée `geostudio-appexport-standalone` :

```yaml
          # SP-21 : ces quatre images existaient uniquement en `build:` dans
          # le compose — donc introuvables au déploiement. `context` et
          # `dockerfile` doivent correspondre **exactement** aux valeurs du
          # compose : c'est ce couple que vérifie
          # tests/test_deployability.py::test_every_build_service_has_a_released_image.
          - image: geostudio-export-worker
            context: ./core
            dockerfile: ../deploy/export-worker/Dockerfile
          - image: geostudio-qgis-worker
            context: ./deploy/qgis-worker
            dockerfile: Dockerfile
          - image: geostudio-appexport-runtime-builder
            context: .
            dockerfile: deploy/appexport-runtime-builder/Dockerfile
          - image: geostudio-backup
            context: ./deploy/backup
            dockerfile: Dockerfile
```

- [ ] **Step 5: Vérifier que les deux tests passent, et que le reste de la suite n'a pas bougé**

```bash
cd core && uv run pytest tests/test_deployability.py -v
cd core && uv run pytest -q
```

Attendu : 2 passed sur le fichier ; `1617 passed, 153 skipped` sur la suite (1615 + les 2 nouveaux).

- [ ] **Step 6: Vérifier que la matrice reste lisible par GitHub Actions**

```bash
cd core && uv run python -c "
import yaml, pathlib
m = yaml.safe_load(pathlib.Path('../.github/workflows/release.yml').read_text())
inc = m['jobs']['build-and-push']['strategy']['matrix']['include']
print(len(inc), 'entrées'); [print(' ', e['image'], '|', e['context'], '|', e['dockerfile']) for e in inc]"
```

Attendu : `8 entrées`, et pour `geostudio-export-worker` le chemin résolu par l'action sera `./core/../deploy/export-worker/Dockerfile` — valide, c'est déjà la forme utilisée par le compose.

- [ ] **Step 7: Commit**

```bash
git add core/tests/test_deployability.py core/pyproject.toml core/uv.lock .github/workflows/release.yml
git commit -m "test(deploy): garde-fou des images publiées + 4 images manquantes dans release.yml

Les images export-worker, qgis-worker, appexport-runtime-builder et backup
n'existaient qu'en \`build:\` — déployer l'export PDF, QGIS, l'export d'apps
ou la sauvegarde exigeait de compiler sur l'hôte de production.

Deux règles, la seconde dans l'autre sens pour que remplacer un build: par
un image: (tâche suivante) satisfasse le contrôle au lieu de le supprimer."
```

---

### Task 2: Overlay de production sans `build:` (chantier 1.2)

**Files:**
- Modify: `core/tests/test_deployability.py` (une règle de plus)
- Modify: `docker-compose.prod.yml`

**Interfaces:**
- Consumes: `services()`, `build_target()`, `BASE`, `PROD` de la tâche 1.
- Produces: rien de nouveau.

- [ ] **Step 1: Écrire la règle**

Ajouter à `core/tests/test_deployability.py` :

```python
def test_prod_overlay_substitutes_every_build_with_an_image():
    """L'overlay de production annonce en en-tête servir des « images depuis
    GHCR (au lieu de build:) ». Tout service construit dans le fichier de
    base doit donc y être substitué par un `image:`, et l'overlay ne doit
    pas introduire de `build:` de son cru."""
    prod = services(PROD)
    not_substituted = [
        name for name, service in services(BASE).items()
        if build_target(service) and not (prod.get(name) or {}).get("image")
    ]
    introduced = [name for name, service in prod.items() if build_target(service)]
    assert not not_substituted, (
        "services encore construits depuis les sources en production : "
        f"{not_substituted}. Ajouter `image: ghcr.io/tlenenao/geostudio-"
        "<nom>:${GEOSTUDIO_VERSION:-latest}` dans docker-compose.prod.yml."
    )
    assert not introduced, (
        f"l'overlay de production introduit lui-même un build: {introduced}."
    )
```

- [ ] **Step 2: Lancer et vérifier l'échec**

```bash
cd core && uv run pytest tests/test_deployability.py::test_prod_overlay_substitutes_every_build_with_an_image -v
```

Attendu : **FAILED**, avec `not_substituted == ['appexport-runtime-builder', 'qgis-worker', 'export-worker']` puis (au second assert, une fois le premier corrigé) `introduced == ['backup']`.

- [ ] **Step 3: Substituer les quatre services dans l'overlay**

Dans `docker-compose.prod.yml`, ajouter les trois services absents (à la suite de `cdc-worker`, avant `shell`). **Ne rien redéclarer d'autre** : Compose fusionne, les profils/commandes/variables du fichier de base sont conservés.

```yaml
  # SP-21 : ces trois services restaient en `build:` (fichier de base), donc
  # non déployables sans compiler sur l'hôte. Leurs `profiles:` restent ceux
  # du fichier de base — substituer l'image n'allume aucune capacité.
  export-worker:
    image: ghcr.io/tlenenao/geostudio-export-worker:${GEOSTUDIO_VERSION:-latest}

  qgis-worker:
    image: ghcr.io/tlenenao/geostudio-qgis-worker:${GEOSTUDIO_VERSION:-latest}

  appexport-runtime-builder:
    image: ghcr.io/tlenenao/geostudio-appexport-runtime-builder:${GEOSTUDIO_VERSION:-latest}
```

Puis, dans le service `backup` du même fichier, remplacer la ligne :

```yaml
    build: ./deploy/backup
```

par :

```yaml
    # SP-21 : `backup` n'existe que dans cet overlay et était le seul service
    # de production encore construit sur place — le mécanisme censé être le
    # dernier rempart contre la perte de données.
    image: ghcr.io/tlenenao/geostudio-backup:${GEOSTUDIO_VERSION:-latest}
```

- [ ] **Step 4: Vérifier que la règle passe, et que la règle 7 de la tâche 1 la garde**

```bash
cd core && uv run pytest tests/test_deployability.py -v
```

Attendu : 3 passed. En particulier `test_every_referenced_ghcr_image_is_released` doit **rester vert** : il vérifie maintenant les 4 nouvelles images contre la matrice de la tâche 1. S'il échoue, un nom d'image ne correspond pas entre l'overlay et `release.yml` — c'est exactement ce que cette règle existe pour attraper.

- [ ] **Step 5: Vérification manuelle avec docker (preuve de sortie du chantier 1.2)**

```bash
cd /home/lenen/projets/geostudio
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile export --profile etl --profile appexport --profile observability \
  config 2>/dev/null | grep -c "build:"
```

Attendu : `0`. Consigner la sortie exacte dans le rapport de tâche. Si `docker` n'est pas disponible dans l'environnement, le dire explicitement dans le rapport — **ne pas** prétendre la vérification faite (précédent SP-15d).

- [ ] **Step 6: Commit**

```bash
git add core/tests/test_deployability.py docker-compose.prod.yml
git commit -m "fix(compose): overlay prod sans build: — 4 services substitués par leur image GHCR

export-worker, qgis-worker, appexport-runtime-builder et backup étaient
encore compilés sur l'hôte de production. Profils inchangés : substituer
l'image n'allume aucune capacité."
```

---

### Task 3: Variables câblées et documentées (chantier 1.5, écart 1 de la spec)

**Files:**
- Modify: `core/tests/test_deployability.py` (deux règles de plus)
- Modify: `docker-compose.yml` (services `core` et `worker`)
- Modify: `.env.example`

**Interfaces:**
- Consumes: `services()`, `BASE`, `PROD`, `CORE_APP`, `ENV_EXAMPLE` de la tâche 1.
- Produces: `core_env_vars() -> set[str]` (réutilisé par la tâche 4 pour les buckets).

- [ ] **Step 1: Écrire les deux règles**

Ajouter à `core/tests/test_deployability.py` :

```python
# Variables lues par le cœur mais légitimement absentes du compose de ce
# dépôt. Liste fermée : toute variable nouvelle est soit câblée, soit
# ajoutée ici avec sa raison — c'est cette contrainte qui a de la valeur.
ENV_WIRING_EXEMPTIONS = {
    # Couture de test : permet de lire des partitions CDC depuis le disque
    # local au lieu de S3 (tests analytiques). Jamais réglée en production.
    "S3_CDC_BUCKET_BASE_URI",
    # Lues par l'image mini-serveur de l'export autoporté (SP-18c), dont le
    # docker-compose est **généré** par build_standalone_bundle_zip et livré
    # dans le zip — pas celui de ce dépôt.
    "APPEXPORT_STANDALONE_DATA_DIR",
    "APPEXPORT_STANDALONE_RUNTIME_DIR",
}

ENV_READ_RE = re.compile(
    r"os\.environ(?:\.get\(|\[)\s*[\"']([A-Z0-9_]+)"
    r"|os\.getenv\(\s*[\"']([A-Z0-9_]+)"
)


def core_env_vars() -> set[str]:
    """Toute variable d'environnement lue par `core/app/`."""
    found = set()
    for module in CORE_APP.rglob("*.py"):
        for direct, via_getenv in ENV_READ_RE.findall(module.read_text()):
            found.add(direct or via_getenv)
    return found


def _wired_env_vars() -> set[str]:
    wired = set()
    for path in (BASE, PROD):
        for service in services(path).values():
            env = service.get("environment") or {}
            if isinstance(env, dict):
                wired |= set(env)
            else:  # forme liste : "VAR=valeur"
                wired |= {item.split("=", 1)[0] for item in env}
    return wired


def test_every_core_env_var_is_wired_to_a_service():
    """Une variable lue par le cœur mais absente de l'environnement de tout
    service est un réglage inatteignable : l'opérateur la met dans son .env,
    rien ne change, aucun signal. C'est le mode d'échec de SP-17a, SP-17b,
    tileset3d — et de CORE_ETL_ENABLED, trouvée par cette règle."""
    unwired = core_env_vars() - _wired_env_vars() - ENV_WIRING_EXEMPTIONS
    assert not unwired, (
        f"variables lues par core/app/ et câblées sur aucun service : "
        f"{sorted(unwired)}. Les ajouter à l'`environment` du service qui "
        "les lit, ou à ENV_WIRING_EXEMPTIONS avec la raison écrite."
    )


def test_every_compose_substitution_is_documented():
    """Toute valeur que l'opérateur doit fournir (`${VAR}`) doit être
    découvrable dans .env.example. La règle ne porte QUE sur les
    substitutions : les valeurs dérivées calculées dans le compose
    (DATABASE_URL, OTEL_*) n'ont rien à y faire — les y mettre inviterait à
    les régler à la main."""
    substitutions = set()
    for path in (BASE, PROD):
        substitutions |= set(re.findall(r"\$\{([A-Z0-9_]+)", path.read_text()))
    documented = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.MULTILINE))
    undocumented = substitutions - documented
    assert not undocumented, (
        f"substitutions de compose absentes de .env.example : {sorted(undocumented)}."
    )
```

- [ ] **Step 2: Lancer et vérifier l'échec de la première, le succès de la seconde**

```bash
cd core && uv run pytest tests/test_deployability.py -v -k "env_var or substitution"
```

Attendu : `test_every_core_env_var_is_wired_to_a_service` **FAILED** avec exactement
`['CORE_ANALYST_SUBS', 'CORE_EMBEDDING_API_KEY', 'CORE_EMBEDDING_API_URL', 'CORE_EMBEDDING_MODEL', 'CORE_EMBEDDING_PROVIDER', 'CORE_ETL_ENABLED']` ;
`test_every_compose_substitution_is_documented` **PASSED** (43 substitutions, 43 documentées — garde-fou pur, à signaler comme tel dans le rapport, pas comme un correctif).

- [ ] **Step 3: Câbler les six variables sur le service `core`**

Dans `docker-compose.yml`, service `core`, bloc `environment:`, après la ligne `CORE_ADMIN_SUBS: ${CORE_ADMIN_SUBS:-}` :

```yaml
      # Rôle analyste (SP-11c) : sans cette ligne, `CORE_ANALYST_SUBS` dans
      # le .env de l'opérateur n'atteignait jamais le process.
      CORE_ANALYST_SUBS: ${CORE_ANALYST_SUBS:-}
      # Capacité ETL (SP-15a). Était documentée dans .env.example et nommée
      # dans un commentaire de ce fichier, mais transmise à aucun service :
      # toute la surface pipelines (REST + MCP + sidecar QGIS + cron) était
      # inatteignable en stack packagée, sans le moindre signal. Doit valoir
      # la même chose ici et sur `worker` (qui consomme la file `etl`) —
      # même exigence que CORE_EXPORT_ENABLED entre core et export-worker.
      CORE_ETL_ENABLED: ${CORE_ETL_ENABLED:-false}
      # Fournisseur d'embeddings de la recherche sémantique (SP-7). Non
      # câblé jusqu'ici : le cœur retombait silencieusement sur son défaut.
      CORE_EMBEDDING_PROVIDER: ${CORE_EMBEDDING_PROVIDER:-}
      CORE_EMBEDDING_API_URL: ${CORE_EMBEDDING_API_URL:-}
      CORE_EMBEDDING_API_KEY: ${CORE_EMBEDDING_API_KEY:-}
      CORE_EMBEDDING_MODEL: ${CORE_EMBEDDING_MODEL:-}
```

- [ ] **Step 4: Câbler les cinq variables pertinentes sur le service `worker`**

Dans `docker-compose.yml`, service `worker`, bloc `environment:`, après `CORE_TILESET3D_MAX_TOTAL_BYTES` :

```yaml
      # Miroir des lignes du service `core` : le worker exécute les jobs
      # d'indexation sémantique (file `search`) et les runs de pipeline
      # (file `etl`). Une valeur divergente entre les deux services produit
      # une capacité à moitié allumée — précédent SP-17a.
      CORE_ETL_ENABLED: ${CORE_ETL_ENABLED:-false}
      CORE_EMBEDDING_PROVIDER: ${CORE_EMBEDDING_PROVIDER:-}
      CORE_EMBEDDING_API_URL: ${CORE_EMBEDDING_API_URL:-}
      CORE_EMBEDDING_API_KEY: ${CORE_EMBEDDING_API_KEY:-}
      CORE_EMBEDDING_MODEL: ${CORE_EMBEDDING_MODEL:-}
```

- [ ] **Step 5: Documenter les cinq variables non documentées**

Dans `.env.example`, à la suite du bloc `CORE_LLM_*` (vers la ligne 57) :

```bash
# Rôle analyste (SP-11c) — subs OIDC autorisés à /analytics/sql, séparés par
# des virgules. Vide = personne.
CORE_ANALYST_SUBS=
# Recherche sémantique (SP-7) — laisser vide pour le fournisseur par défaut
# (hachage local, sans réseau). `openai` exige les trois lignes suivantes.
CORE_EMBEDDING_PROVIDER=
CORE_EMBEDDING_API_URL=
CORE_EMBEDDING_API_KEY=
CORE_EMBEDDING_MODEL=
```

`CORE_ETL_ENABLED` est déjà documentée (ligne 82) — ne pas la dupliquer.

- [ ] **Step 6: Vérifier le vert et l'absence d'effet de bord**

```bash
cd core && uv run pytest tests/test_deployability.py -v
cd core && uv run pytest -q
```

Attendu : 5 passed sur le fichier, `1620 passed, 153 skipped` sur la suite.

Vérification manuelle (docker requis) que la valeur arrive bien, et que le défaut reste éteint :

```bash
cd /home/lenen/projets/geostudio
docker compose config 2>/dev/null | grep -A2 "CORE_ETL_ENABLED"
CORE_ETL_ENABLED=true docker compose config 2>/dev/null | grep "CORE_ETL_ENABLED"
```

Attendu : `false` pour les deux services sans variable d'environnement, `true` pour les deux avec. Consigner ; si docker est indisponible, le dire.

- [ ] **Step 7: Commit**

```bash
git add core/tests/test_deployability.py docker-compose.yml .env.example
git commit -m "fix(compose): câble 6 variables inatteignables, dont CORE_ETL_ENABLED

CORE_ETL_ENABLED était documentée dans .env.example et citée dans un
commentaire du compose, mais transmise à aucun service : toute la surface
SP-15 (pipelines REST+MCP, 13 opérations, sidecar QGIS, planification) était
éteinte quoi que l'opérateur mette dans son .env. 4e occurrence de la classe
de bug qui motive cette vague, et la plus large.

Idem pour les 4 CORE_EMBEDDING_* (recherche sémantique SP-7) et
CORE_ANALYST_SUBS (rôle analyste SP-11c). Défauts inchangés : aucune
capacité ne s'allume."
```

---

### Task 4: Périmètre de sauvegarde (chantier 1.3)

**Files:**
- Modify: `core/tests/test_deployability.py` (une règle de plus)
- Modify: `deploy/backup/backup.sh`
- Modify: `docker-compose.prod.yml` (service `backup`)
- Modify: `.env.example`
- Modify: `docs/runbooks/2026-07-24-restauration-sauvegardes.md`

**Interfaces:**
- Consumes: `core_env_vars()` (tâche 3), `BACKUP_SH` (tâche 1).

- [ ] **Step 1: Écrire la règle**

Ajouter à `core/tests/test_deployability.py` :

```python
# Buckets volontairement hors sauvegarde, avec la raison. `exports` et
# `appexports` ne contiennent que des artefacts régénérables : un PDF de
# rapport ou un bundle d'app se re-demande en un clic.
BACKUP_EXCLUDED_BUCKETS = {
    "S3_EXPORTS_BUCKET",
    "S3_APPEXPORTS_BUCKET",
}


def test_backup_covers_every_bucket_the_core_uses():
    """Un bucket utilisé par le cœur et absent de la sauvegarde produit le
    pire mode d'échec possible : après restauration, l'item réapparaît
    intact en pointant sur une clé S3 disparue — cassé pour toujours, sans
    erreur au moment de la restauration. Le cas réel est `tileset3d` : un
    tileset uploadé est un objet S3 jamais extrait, sans autre copie."""
    used = {v for v in core_env_vars() if v.startswith("S3_") and v.endswith("_BUCKET")}
    mirrored = set(re.findall(r"\$\{(S3_[A-Z0-9_]*_BUCKET)", BACKUP_SH.read_text()))
    missing = used - mirrored - BACKUP_EXCLUDED_BUCKETS
    assert not missing, (
        f"buckets utilisés par le cœur et jamais sauvegardés : {sorted(missing)}. "
        "Les ajouter à la boucle de miroir de deploy/backup/backup.sh, ou à "
        "BACKUP_EXCLUDED_BUCKETS avec la raison écrite."
    )
```

- [ ] **Step 2: Lancer et vérifier l'échec**

```bash
cd core && uv run pytest tests/test_deployability.py::test_backup_covers_every_bucket_the_core_uses -v
```

Attendu : **FAILED** avec exactement `['S3_TERRAIN3D_BUCKET', 'S3_TILESET3D_BUCKET']`.

- [ ] **Step 3: Étendre la boucle de miroir**

Dans `deploy/backup/backup.sh`, remplacer le bloc de la section « 2. MinIO » :

```bash
# ── 2. MinIO (miroir des 3 buckets applicatifs) ──
mc alias set local http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" >/dev/null
mkdir -p "${WORKDIR}/minio"
for bucket in "${S3_THUMBNAILS_BUCKET:-geostudio-thumbnails}" \
              "${S3_UPLOADS_BUCKET:-geostudio-uploads}" \
              "${S3_CDC_BUCKET:-geostudio-cdc}"; do
```

par :

```bash
# ── 2. MinIO (miroir des buckets de données) ──
#
# Périmètre : les cinq buckets dont le contenu est IRREMPLAÇABLE.
#   - thumbnails/uploads : fichiers déposés par les utilisateurs ;
#   - cdc : journal de réplication, socle de tout l'analytique ;
#   - tileset3d/terrain3d : un tileset 3D ou un COG de terrain uploadé est
#     un objet S3 JAMAIS extrait, sans autre copie, dont les métadonnées
#     vivent dans BuilderConfig. Sans lui, la restauration fait réapparaître
#     l'item intact en pointant sur une clé disparue — cassé pour toujours,
#     et sans erreur au moment de la restauration (SP-21, chantier 1.3).
#
# Volontairement EXCLUS, et c'est écrit ici pour que ça ne se redécouvre
# pas : `exports` et `appexports` ne contiennent que des artefacts
# régénérables (un PDF de rapport, un bundle d'app se re-demandent). Toute
# exclusion nouvelle doit aussi être déclarée dans
# core/tests/test_deployability.py::BACKUP_EXCLUDED_BUCKETS.
mc alias set local http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" >/dev/null
mkdir -p "${WORKDIR}/minio"
for bucket in "${S3_THUMBNAILS_BUCKET:-geostudio-thumbnails}" \
              "${S3_UPLOADS_BUCKET:-geostudio-uploads}" \
              "${S3_CDC_BUCKET:-geostudio-cdc}" \
              "${S3_TILESET3D_BUCKET:-geostudio-tileset3d}" \
              "${S3_TERRAIN3D_BUCKET:-geostudio-terrain3d}"; do
```

- [ ] **Step 4: Passer les deux buckets au service `backup`**

Dans `docker-compose.prod.yml`, service `backup`, bloc `environment:`, après `S3_CDC_BUCKET: geostudio-cdc` :

```yaml
      S3_TILESET3D_BUCKET: geostudio-tileset3d
      S3_TERRAIN3D_BUCKET: geostudio-terrain3d
```

- [ ] **Step 5: Rendre les trois buckets non documentés découvrables**

Dans `.env.example`, à la suite du bloc `S3_*_BUCKET` existant (vers la ligne 65) :

```bash
# Buckets fixés en dur dans docker-compose.yml (pas de substitution) —
# listés ici pour être découvrables, pas pour être réglés. Les changer exige
# de modifier le compose ET deploy/backup/backup.sh.
#   S3_CDC_BUCKET=geostudio-cdc                (sauvegardé)
#   S3_EXPORTS_BUCKET=geostudio-exports        (NON sauvegardé — régénérable)
#   S3_APPEXPORTS_BUCKET=geostudio-appexports  (NON sauvegardé — régénérable)
```

- [ ] **Step 6: Écrire le périmètre dans le runbook**

Dans `docs/runbooks/2026-07-24-restauration-sauvegardes.md`, à la fin de la section `## Prérequis`, ajouter :

```markdown
## Périmètre de la sauvegarde (ce qui revient, et ce qui ne revient pas)

**Restauré** : la base Postgres complète (donc aussi les comptes Keycloak,
même base `gis`), et cinq buckets MinIO — `thumbnails`, `uploads`, `cdc`,
`tileset3d`, `terrain3d`.

**Volontairement non restauré** : les buckets `exports` et `appexports`. Ils
ne contiennent que des artefacts régénérables — un PDF de rapport planifié,
un bundle d'export d'app. Après restauration, un lien de téléchargement
émis avant la perte sera mort : c'est attendu, l'export se re-demande.

**Non prouvé à ce jour (SP-21)** : ce runbook n'a **jamais été rejoué de bout
en bout**. Le périmètre ci-dessus est vérifié mécaniquement
(`core/tests/test_deployability.py`), mais personne n'a encore observé une
restauration réussie — en particulier, personne n'a vérifié qu'un item
`tileset3d` reste affichable après restauration. C'est le chantier 1.4 du
plan d'action, renvoyé à la vague 2.
```

- [ ] **Step 7: Vérifier le vert**

```bash
cd core && uv run pytest tests/test_deployability.py -v
bash -n deploy/backup/backup.sh && echo "backup.sh syntaxiquement valide"
```

Attendu : 6 passed ; `backup.sh syntaxiquement valide`.

- [ ] **Step 8: Commit**

```bash
git add core/tests/test_deployability.py deploy/backup/backup.sh docker-compose.prod.yml .env.example docs/runbooks/2026-07-24-restauration-sauvegardes.md
git commit -m "fix(backup): sauvegarde tileset3d et terrain3d, exclusions écrites

Un tileset 3D uploadé est un objet S3 jamais extrait, sans autre copie :
sans lui, la restauration fait réapparaître l'item intact en pointant sur
une clé disparue — cassé définitivement, sans erreur visible.

exports/appexports restent exclus, mais explicitement (script, runbook,
test). Le runbook dit désormais que la restauration n'a jamais été rejouée."
```

---

### Task 5: Pinning des images (chantier 1.6, premier volet)

**Files:**
- Modify: `core/tests/test_deployability.py` (une règle de plus)
- Modify: `docker-compose.yml` (`minio`, `keycloak`, `traefik`)
- Modify: `docker-compose.prod.yml` (`tunnel`)

**Interfaces:**
- Consumes: `services()`, `BASE`, `PROD` de la tâche 1.

- [ ] **Step 1: Écrire la règle**

Ajouter à `core/tests/test_deployability.py` :

```python
# Un tag « flottant » : v3.0 suit tous les patches à venir, 24.0 aussi. La
# règle est une liste noire volontaire (absence de tag, `latest`, mineur
# flottant) et non une exigence de forme : des tags parfaitement pinnés ne
# sont pas semver (minio publie RELEASE.2025-09-07T16-13-09Z, pgbouncer
# 1.22.1-p0), et une exigence de forme les rejetterait à tort.
FLOATING_TAG_RE = re.compile(r"^v?\d+\.\d+$")


def test_images_are_pinned():
    """Une image sans tag, en `latest`, ou pinnée au mineur, change sous les
    pieds de l'opérateur : deux `docker compose pull` à un mois d'écart ne
    donnent pas la même stack, et un incident devient irreproductible."""
    unpinned = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            image = service.get("image")
            if not image or "${" in image:
                continue  # nos propres images : pinnées par le tag de release
            _, _, tag = image.rpartition(":")
            if tag == image or not tag:
                unpinned[f"{path.name}:{name}"] = f"{image} (aucun tag)"
            elif tag == "latest":
                unpinned[f"{path.name}:{name}"] = f"{image} (latest)"
            elif FLOATING_TAG_RE.fullmatch(tag):
                unpinned[f"{path.name}:{name}"] = f"{image} (mineur flottant)"
    assert not unpinned, (
        f"images non pinnées : {unpinned}. Résoudre le tag exact contre le "
        "registre — jamais l'inventer (précédent SP-15d : qgis/qgis:latest "
        "pointait vers un build 4.3.0-master instable)."
    )
```

- [ ] **Step 2: Lancer et vérifier l'échec**

```bash
cd core && uv run pytest tests/test_deployability.py::test_images_are_pinned -v
```

Attendu : **FAILED** avec exactement ces quatre entrées — `docker-compose.yml:minio` → `minio/minio (aucun tag)`, `docker-compose.yml:keycloak` → `quay.io/keycloak/keycloak:24.0 (mineur flottant)`, `docker-compose.yml:traefik` → `traefik:v3.0 (mineur flottant)`, `docker-compose.prod.yml:tunnel` → `tailscale/tailscale:latest (latest)`.

- [ ] **Step 3: Re-résoudre les quatre tags contre les registres**

Les valeurs ci-dessous ont été résolues le 2026-08-20. **Rejouer les commandes** : si une sortie diffère, c'est elle qui gagne.

```bash
curl -s "https://hub.docker.com/v2/repositories/minio/minio/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import json,sys; print([t['name'] for t in json.load(sys.stdin)['results'] if t['name'].startswith('RELEASE.') and not t['name'].endswith('-cpuv1')][:3])"
curl -s "https://hub.docker.com/v2/repositories/library/traefik/tags?page_size=100&name=v3.0" \
  | python3 -c "import json,sys,re; print(sorted({t['name'] for t in json.load(sys.stdin)['results'] if re.fullmatch(r'v3\.0\.\d+', t['name'])})[-1])"
curl -s "https://quay.io/api/v1/repository/keycloak/keycloak/tag/?limit=100&onlyActiveTags=true&filter_tag_name=like:24.0" \
  | python3 -c "import json,sys,re; print(sorted({t['name'] for t in json.load(sys.stdin)['tags'] if re.fullmatch(r'24\.0\.\d+', t['name'])}, key=lambda s:int(s.split('.')[-1]))[-1])"
curl -s "https://hub.docker.com/v2/repositories/tailscale/tailscale/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import json,sys,re; print([t['name'] for t in json.load(sys.stdin)['results'] if re.fullmatch(r'v\d+\.\d+\.\d+', t['name'])][0])"
```

Valeurs attendues (résolues le 2026-08-20) : `RELEASE.2025-09-07T16-13-09Z`, `v3.0.4`, `24.0.5`, `v1.102.3`.

- [ ] **Step 4: Appliquer les quatre pins**

`docker-compose.yml` :

```yaml
# service minio, remplacer  image: minio/minio
    # Pin explicite (SP-21) : cette ligne était sans tag, donc `latest` —
    # le stockage objet de toutes les données du produit changeait de
    # version à chaque pull.
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z

# service keycloak, remplacer  image: quay.io/keycloak/keycloak:24.0
    image: quay.io/keycloak/keycloak:24.0.5

# service traefik, remplacer  image: traefik:v3.0
    image: traefik:v3.0.4
```

`docker-compose.prod.yml` :

```yaml
# service tunnel, remplacer  image: tailscale/tailscale:latest
    image: tailscale/tailscale:v1.102.3
```

- [ ] **Step 5: Vérifier le vert et l'existence réelle des tags**

```bash
cd core && uv run pytest tests/test_deployability.py -v
cd /home/lenen/projets/geostudio
for i in minio/minio:RELEASE.2025-09-07T16-13-09Z traefik:v3.0.4 quay.io/keycloak/keycloak:24.0.5 tailscale/tailscale:v1.102.3; do
  docker manifest inspect "$i" >/dev/null 2>&1 && echo "OK   $i" || echo "ABSENT $i"
done
docker compose config 2>/dev/null | grep -c ":latest"
```

Attendu : 7 passed ; quatre `OK` ; `0` occurrence de `:latest`. Le test de forme ne prouve **pas** l'existence du tag — c'est ce que fait `docker manifest inspect`, et c'est pour ça que cette étape existe. Si docker est indisponible, le dire dans le rapport et signaler que l'existence des tags reste non vérifiée.

- [ ] **Step 6: Commit**

```bash
git add core/tests/test_deployability.py docker-compose.yml docker-compose.prod.yml
git commit -m "fix(compose): pin minio, traefik, keycloak et tailscale au patch

minio/minio était déclaré sans aucun tag (donc latest) pour le stockage de
toutes les données du produit. Les quatre tags sont résolus contre leur
registre, pas inventés."
```

---

### Task 6: Healthchecks des quatre services applicatifs (chantier 1.6, second volet)

**Files:**
- Create: `core/scripts/healthcheck_cdc.py`
- Create: `core/tests/test_healthcheck_cdc.py`
- Modify: `docker-compose.yml` (`core`, `worker`, `cdc-worker`, `shell`, `export-worker`)

**Interfaces:**
- Produces: `core/scripts/healthcheck_cdc.py` exposant `slot_is_active(connection, slot_name: str) -> bool` et `main() -> int`.
- Consumes: rien des tâches précédentes.

- [ ] **Step 1: Écrire le test de la sonde CDC**

Créer `core/tests/test_healthcheck_cdc.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité du worker CDC (SP-21, chantier 1.6).

Un `docker healthcheck` qui ne vérifie que la présence du process ne détecte
pas le cas que I5 nomme explicitement — « un worker vivant mais bloqué ».
Pour le CDC, il existe un signal serveur direct et fiable :
`pg_replication_slots.active`, à true seulement tant qu'un consommateur tient
le slot. C'est ce que teste cette sonde."""
import pytest

from scripts.healthcheck_cdc import SLOT_NAME, slot_is_active


class _FakeConnection:
    """Assez de `psycopg` pour cette sonde : `execute(...).fetchone()`."""

    def __init__(self, row):
        self._row = row
        self.executed: list[tuple] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self._row


def test_slot_is_active_when_a_consumer_holds_it():
    conn = _FakeConnection((True,))
    assert slot_is_active(conn, SLOT_NAME) is True
    sql, params = conn.executed[0]
    assert "pg_replication_slots" in sql
    assert params == (SLOT_NAME,)  # jamais interpolé dans le SQL


def test_slot_is_inactive_when_nobody_consumes_it():
    """Le cas qui compte : le slot existe (donc le WAL s'accumule) mais
    personne ne le draine — process vivant, réplication morte."""
    assert slot_is_active(_FakeConnection((False,)), SLOT_NAME) is False


def test_missing_slot_is_not_healthy():
    """Slot absent : le worker n'a pas encore fini son `ensure_replication_slot`,
    ou il a échoué. Dans les deux cas, pas sain."""
    assert slot_is_active(_FakeConnection(None), SLOT_NAME) is False


def test_slot_name_matches_the_consumer():
    """Une divergence de nom rendrait la sonde toujours rouge — donc, avec un
    depends_on, bloquerait la stack."""
    from app.cdc.consumer import SLOT_NAME as consumer_slot

    assert SLOT_NAME == consumer_slot


def test_main_returns_non_zero_without_a_dsn(monkeypatch):
    from scripts.healthcheck_cdc import main

    monkeypatch.delenv("CDC_DATABASE_URL", raising=False)
    assert main() == 1
```

- [ ] **Step 2: Lancer et vérifier l'échec**

```bash
cd core && uv run pytest tests/test_healthcheck_cdc.py -v
```

Attendu : **collection error** — `ModuleNotFoundError: No module named 'scripts.healthcheck_cdc'`.

- [ ] **Step 3: Écrire la sonde**

Créer `core/scripts/healthcheck_cdc.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sonde de vivacité du worker CDC, pour le `healthcheck` de son service.

Pourquoi pas une sonde de process : `python -m app.cdc.main` peut être vivant
et ne rien consommer (boucle bloquée, exception avalée dans une tâche), et
c'est exactement le cas que I5 du plan d'action 2026-08-20 signale. Le slot
de réplication donne le signal côté serveur : `active` n'est true que tant
qu'un consommateur le tient.

Usage (healthcheck docker) : `python -m scripts.healthcheck_cdc`
Sortie 0 = sain, 1 = pas sain.
"""
import os
import sys

from app.cdc.consumer import SLOT_NAME

__all__ = ["SLOT_NAME", "main", "slot_is_active"]

QUERY = "select active from pg_replication_slots where slot_name = %s"


def slot_is_active(connection, slot_name: str) -> bool:
    row = connection.execute(QUERY, (slot_name,)).fetchone()
    return bool(row and row[0])


def main() -> int:
    dsn = os.environ.get("CDC_DATABASE_URL")
    if not dsn:
        print("CDC_DATABASE_URL absent", file=sys.stderr)
        return 1
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            return 0 if slot_is_active(connection, SLOT_NAME) else 1
    except Exception as exc:  # une sonde ne doit jamais lever, seulement échouer
        print(f"sonde CDC en échec : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Vérifier le vert**

```bash
cd core && uv run pytest tests/test_healthcheck_cdc.py -v
```

Attendu : 5 passed. Si `test_slot_name_matches_the_consumer` échoue, c'est le nom du slot qui a changé dans `app/cdc/consumer.py` — corriger l'import, jamais la constante.

- [ ] **Step 5: Ajouter les quatre healthchecks**

Dans `docker-compose.yml`. Service `core`, après le bloc `environment:` (au même niveau que `ports:`) :

```yaml
    # `start_period` généreux : ce service applique les migrations Alembic
    # avant de servir (cf. `command:`), et rien n'attendait la fin de cette
    # étape avant de router vers lui (I5 du plan d'action 2026-08-20).
    # `python`, pas `curl` : l'image est python:3.12-slim, sans curl.
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8200/health').read()"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 90s
```

Service `worker` :

```yaml
    # `procrastinate healthchecks` vérifie la connexion et le schéma de la
    # file. Limite connue et assumée : un worker occupé par une tâche qui ne
    # rend jamais la main reste « healthy » — cette sonde détecte un worker
    # mort ou déconnecté de la base, pas un worker coincé.
    healthcheck:
      test: ["CMD", "python", "-m", "procrastinate", "--app", "app.jobs.app", "healthchecks"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

Service `cdc-worker` :

```yaml
    # Sonde côté serveur (scripts/healthcheck_cdc.py) : le slot de
    # réplication n'est `active` que tant qu'un consommateur le tient. Seule
    # des quatre à détecter le « vivant mais ne consomme plus ».
    healthcheck:
      test: ["CMD", "python", "-m", "scripts.healthcheck_cdc"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

Service `shell` :

```yaml
    # `wget` de busybox — l'image est nginx:1.27-alpine, sans curl.
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://localhost:8300/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 6: Rendre la dépendance à `core` bloquante là où elle a un sens**

Dans `docker-compose.yml`, service `shell`, remplacer sa ligne `depends_on: [core]` (ou ajouter le bloc s'il n'existe pas) par :

```yaml
    # Attend que `core` ait fini ses migrations et réponde : le shell sans
    # cœur n'affiche qu'une page d'erreur. Dépendance dure volontairement
    # limitée à `shell` et `export-worker` — SP-18a a dû *retirer* celle de
    # `worker` parce qu'elle bloquait le démarrage pour une capacité
    # désactivée par défaut.
    depends_on:
      core:
        condition: service_healthy
```

Et service `export-worker`, remplacer `depends_on: [pgbouncer, minio]` par :

```yaml
    depends_on:
      pgbouncer:
        condition: service_started
      minio:
        condition: service_healthy
      core:
        condition: service_healthy
```

- [ ] **Step 7: Vérifier la forme du compose et la cohérence des sondes**

```bash
cd core && uv run pytest tests/test_deployability.py tests/test_healthcheck_cdc.py -q
cd /home/lenen/projets/geostudio && docker compose config 2>/dev/null | grep -c "healthcheck"
```

Attendu : 12 passed ; au moins 7 blocs `healthcheck` dans le compose résolu (3 existants + 4 nouveaux).

Vérification que chaque commande de sonde existe bien dans son image (docker requis) :

```bash
docker compose run --rm --no-deps --entrypoint python core -m procrastinate --app app.jobs.app healthchecks; echo "code=$?"
docker compose run --rm --no-deps --entrypoint sh shell -c 'command -v wget'
```

Attendu : la première commande peut échouer faute de base démarrée (`code=1`) — ce qui prouve qu'elle **s'exécute**, le seul point à vérifier ici ; `command -v wget` doit imprimer un chemin. Consigner les deux sorties ; si docker est indisponible, marquer les sondes comme non vérifiées à l'exécution dans le rapport.

- [ ] **Step 8: Commit**

```bash
git add core/scripts/healthcheck_cdc.py core/tests/test_healthcheck_cdc.py docker-compose.yml
git commit -m "feat(compose): healthchecks sur core, worker, cdc-worker et shell

Rien n'attendait la fin des migrations Alembic avant de router vers core
(I5). La sonde CDC interroge pg_replication_slots.active : seule des quatre
à détecter un worker vivant mais qui ne consomme plus. Dépendance dure
limitée à shell et export-worker, pour ne pas rejouer le blocage de
démarrage retiré en SP-18a."
```

---

### Task 7: Healthchecks des trois services d'infrastructure (chantier 1.6, troisième volet)

**Files:**
- Modify: `docker-compose.yml` (`pgbouncer`, `martin`, `titiler` — selon découverte)

**Interfaces:**
- Consumes: rien.

Cette tâche est une **découverte suivie d'une décision**, pas une écriture aveugle : une sonde qui appelle un binaire absent de l'image marque le service `unhealthy` pour toujours. Aucune de ces trois images n'a été inspectée à ce jour.

- [ ] **Step 1: Inspecter les trois images**

```bash
cd /home/lenen/projets/geostudio
for svc in pgbouncer martin titiler; do
  echo "=== $svc ==="
  docker compose run --rm --no-deps --entrypoint sh "$svc" -c 'for b in curl wget python3 psql nc; do command -v $b; done' 2>&1 | tail -5
done
```

Noter, pour chaque service, quels binaires existent. Si l'image n'a pas de shell (`sh` absent → l'`--entrypoint sh` échoue), c'est une réponse aussi : **aucune** sonde n'est possible sans en construire une image dérivée, ce qui est hors périmètre.

- [ ] **Step 2: Ajouter une sonde uniquement là où un binaire le permet**

Cibles applicatives, à utiliser avec le binaire trouvé :
- `pgbouncer` : `psql -h 127.0.0.1 -p 6432 -U gis -d pgbouncer -c "show version"` si `psql` existe ; sinon `nc -z 127.0.0.1 6432`.
- `martin` : `http://localhost:3000/health` (endpoint natif de martin).
- `titiler` : `http://localhost:8000/healthz` (endpoint natif de titiler).

Modèle à recopier, en remplaçant `<commande>` :

```yaml
    healthcheck:
      test: ["CMD", <commande>]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 3: Documenter chaque omission**

Pour tout service laissé sans healthcheck, ajouter un commentaire au-dessus de son `image:` disant **pourquoi** :

```yaml
    # Pas de healthcheck (SP-21) : l'image ne fournit aucun binaire utilisable
    # comme sonde (vérifié : <sortie de l'étape 1>). Une sonde exigerait une
    # image dérivée — hors périmètre de cette vague.
```

Le rapport de tâche doit lister explicitement les services sondés et les services omis. Une omission documentée est un résultat acceptable ; une sonde inventée qui ne s'exécute pas ne l'est pas.

- [ ] **Step 4: Vérifier**

```bash
cd core && uv run pytest tests/test_deployability.py -q
cd /home/lenen/projets/geostudio && docker compose up -d postgis pgbouncer minio martin titiler && sleep 45 && docker compose ps
```

Attendu : aucun des services sondés n'est en `unhealthy`. Un `unhealthy` ici signifie que la sonde est fausse — la retirer plutôt que la garder.

```bash
docker compose down
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(compose): healthchecks pgbouncer/martin/titiler là où l'image le permet

Sondes vérifiées à l'exécution image par image ; toute omission porte la
raison en commentaire. Une sonde qui appelle un binaire absent marque le
service unhealthy pour toujours — pire que pas de sonde."
```

---

### Task 8: Notice GPL de l'image `qgis-worker` publiée (chantier 1.1, volet gouvernance)

**Files:**
- Create: `deploy/qgis-worker/LICENSE-QGIS.md`
- Modify: `deploy/qgis-worker/Dockerfile`
- Create: `docs/ops/redistribution-images.md`

**Interfaces:**
- Consumes: la matrice de release de la tâche 1 (l'image est désormais publiée).

Publier `geostudio-qgis-worker` sur `ghcr.io` est un **acte de distribution** de QGIS et de GRASS, tous deux sous GPL. Cela ne change rien à la licence du cœur (Apache-2.0, image séparée, aucun lien de code — arbitrage A39 intact), mais l'image distribuée doit porter la notice. Aucun document du dépôt ne couvrait ce cas : le seul écrit existant est l'arbitrage d'**isolation**, pas la **redistribution**.

- [ ] **Step 1: Écrire la notice embarquée**

Créer `deploy/qgis-worker/LICENSE-QGIS.md` :

```markdown
# Licences des composants de cette image

Cette image est publiée par le projet GeoStudio (Apache-2.0) et **contient
des logiciels sous GNU GPL** :

- **QGIS** (`qgis/qgis:release-3_34`, QGIS 3.34 LTR) — GPL-2.0-or-later.
  Sources amont : <https://github.com/qgis/QGIS>, tag correspondant à
  QGIS 3.34.
- **GRASS GIS** (fourni par l'image amont, plugin `grassprovider` activé) —
  GPL-2.0-or-later. Sources amont : <https://github.com/OSGeo/grass>.

GeoStudio n'apporte aucune modification à ces logiciels. Les seuls fichiers
ajoutés par-dessus l'image amont sont `server.py` et `allowlist.txt`,
publiés sous Apache-2.0 dans le dépôt GeoStudio
(<https://github.com/tlenenao/geostudio>, `deploy/qgis-worker/`).

Les termes GPL s'appliquent à QGIS et GRASS tels que distribués ici. Le
cœur de GeoStudio (`core/`) reste sous Apache-2.0 : il n'est pas lié à QGIS,
il dialogue avec ce conteneur par HTTP, en sous-processus isolé et sans
credential (arbitrage A39).
```

- [ ] **Step 2: Embarquer la notice dans l'image**

Dans `deploy/qgis-worker/Dockerfile`, après la ligne `COPY allowlist.txt /app/allowlist.txt` :

```dockerfile
# Cette image est désormais PUBLIÉE sur ghcr.io (SP-21) — c'est un acte de
# distribution de QGIS et GRASS, tous deux sous GPL. La notice voyage donc
# avec l'image, pas seulement dans le dépôt.
COPY LICENSE-QGIS.md /LICENSE-QGIS.md
LABEL org.opencontainers.image.licenses="GPL-2.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Sidecar QGIS Processing pour GeoStudio — contient QGIS et GRASS (GPL). Voir /LICENSE-QGIS.md."
```

- [ ] **Step 3: Écrire la note de redistribution**

Créer `docs/ops/redistribution-images.md` :

```markdown
# Redistribution des images publiées

GeoStudio publie 8 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
(cf. `.github/workflows/release.yml`). Sept d'entre elles ne contiennent que
du code GeoStudio (Apache-2.0) et des dépendances permissives.

## `geostudio-qgis-worker` — contient du GPL

Cette image dérive de `qgis/qgis:release-3_34` et contient **QGIS** et
**GRASS GIS**, sous GPL-2.0-or-later. La publier est un acte de
distribution : l'image embarque `/LICENSE-QGIS.md` (notice + pointeurs vers
les sources amont) et porte les labels OCI correspondants.

GeoStudio ne modifie ni QGIS ni GRASS. Les deux seuls fichiers ajoutés
(`server.py`, `allowlist.txt`) sont publics dans ce dépôt sous Apache-2.0 :
l'offre de source est donc satisfaite par référence, forme usuelle pour une
image dérivée sans modification de l'amont.

**Ce que cela ne change pas** : le cœur GeoStudio (`core/`) reste
Apache-2.0. Il n'est pas lié à QGIS — il appelle ce conteneur en HTTP, isolé,
sans credential de base de données ni accès réseau externe (arbitrage A39).
La capacité est de surcroît éteinte par défaut (`CORE_ETL_ENABLED=false`,
profil compose `etl`).

## Avant d'ajouter une image à la matrice de release

Vérifier la licence de l'image de base. Si elle est copyleft, ajouter ici sa
section et embarquer une notice dans l'image, comme ci-dessus.
```

- [ ] **Step 4: Vérifier que l'image se construit toujours**

```bash
cd /home/lenen/projets/geostudio && docker build -t geostudio-qgis-worker-ci ./deploy/qgis-worker && docker run --rm geostudio-qgis-worker-ci head -3 /LICENSE-QGIS.md
```

Attendu : build réussi, et les trois premières lignes de la notice s'affichent. Si l'environnement ne peut pas construire cette image (~2–3 Gio), le dire dans le rapport et vérifier au minimum que le `COPY` cible un fichier qui existe (`ls deploy/qgis-worker/LICENSE-QGIS.md`).

- [ ] **Step 5: Commit**

```bash
git add deploy/qgis-worker/LICENSE-QGIS.md deploy/qgis-worker/Dockerfile docs/ops/redistribution-images.md
git commit -m "docs(legal): notice GPL dans l'image qgis-worker désormais publiée

Publier cette image sur ghcr.io est un acte de distribution de QGIS et
GRASS (GPL) : la notice et les labels OCI voyagent avec l'image, et
docs/ops/redistribution-images.md dit quoi vérifier avant d'ajouter une
image à la matrice. Le cœur reste Apache-2.0 (A39 inchangé)."
```

---

### Task 9: Clôture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Lancer la suite complète et la CI locale**

```bash
cd core && uv run pytest -q && uv run lint-imports
cd shell && npm run build
```

Attendu : `1632 passed, 153 skipped` (1615 + 12 de `test_deployability.py`/`test_healthcheck_cdc.py`, ajuster selon le compte réel), `Contracts: 1 kept, 0 broken`, build shell vert. Le build shell est là pour prouver l'absence d'effet de bord : aucune tâche n'a touché `shell/`.

- [ ] **Step 2: Vérifier qu'aucun type d'API n'a bougé**

```bash
cd core && uv run python scripts/export_openapi.py /tmp/openapi-sp21.json && cd ../shell && npm run gen:api-types && git diff --exit-code -- src/api/generated/core-schema.d.ts && echo "aucune dérive de types"
```

Attendu : `aucune dérive de types`. Un diff ici signifie qu'une tâche est sortie du périmètre.

- [ ] **Step 3: Documenter SP-21 dans CLAUDE.md**

Dans la section `### Fait`, après l'entrée **SP-20**, ajouter une entrée **SP-21** couvrant : les 7 règles du garde-fou et leur état initial ; les 4 images ajoutées à la release et l'overlay complété ; les 6 variables câblées avec le détail de `CORE_ETL_ENABLED` (4ᵉ occurrence de la classe, la plus large, et le fait que sa présence dans `.env.example` faisait croire au câblage) ; les 2 buckets sauvegardés et les 2 exclus explicitement ; les 4 pins ; les healthchecks posés **et** ceux omis avec leur raison ; la notice GPL.

Dans `### Suivis non bloquants ouverts`, ajouter les limites réelles :

```markdown
- SP-21, suivis non bloquants : la restauration n'a **jamais été rejouée**
  (chantier 1.4 renvoyé en vague 2) — le périmètre de sauvegarde est vérifié
  mécaniquement, mais personne n'a observé une restauration réussie, en
  particulier pour un item `tileset3d`. Le garde-fou lit des YAML : il ne
  démarre rien, ne prouve pas qu'un tag existe au registre (seul
  `docker manifest inspect`, exécuté à la main en tâche 5, le fait), et ne
  prouve pas qu'un `docker compose pull && up` de l'overlay complet
  fonctionne. La sonde du service `worker` ne détecte pas un worker coincé
  sur une tâche qui ne rend jamais la main. Le pinning au patch crée une
  dette d'entretien assumée : aucun outil de mise à jour automatique.
```

Mettre aussi à jour la ligne `uv run pytest` de la section « Commandes » avec le compte réel mesuré.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(sp21): documente SP-21 (déployabilité) dans CLAUDE.md"
```

- [ ] **Step 5: Revue finale de branche**

Invoquer `superpowers:requesting-code-review` sur l'ensemble de la branche. Points à faire regarder en priorité, parce qu'ils sont invisibles tâche par tâche :

1. le compose **résolu** (`docker compose config`, base et overlay, tous profils) — pas seulement les fichiers source : c'est le niveau où les trois incidents historiques se sont cachés ;
2. la cohérence des 4 nouveaux noms d'images entre `release.yml` et l'overlay (une faute de frappe rend l'image introuvable au `pull`, et la règle 7 ne l'attrape que si le préfixe `ghcr.io/.../geostudio-` est respecté) ;
3. les `depends_on: service_healthy` ajoutés : chercher un cycle ou un service qui ne devient jamais `healthy` avec les profils par défaut ;
4. les exemptions déclarées (`ENV_WIRING_EXEMPTIONS`, `BACKUP_EXCLUDED_BUCKETS`) : chacune est-elle encore vraie, ou l'a-t-on utilisée pour faire taire un vrai défaut ?

## Self-Review du plan

**Couverture de la spec** — §4.1 (forme du garde-fou) → tâche 1 ; §4.2 (les 6 règles) → tâches 1→5, plus une 7ᵉ règle justifiée en tête de plan ; §4.3 (câblage) → tâche 3 ; §4.4 (sauvegarde) → tâche 4 ; §4.5 (images, overlay, licence) → tâches 1, 2, 8 ; §4.6 (pins, healthchecks, `depends_on`) → tâches 5, 6, 7 ; §5 (ordre) → écart assumé et justifié en tête ; §6 (preuves) → étapes de vérification manuelle des tâches 2, 3, 5, 6, 7 ; §7 (risques) → tâche 9, étape 3.

**Placeholders** — aucun « TBD ». La seule décision laissée ouverte est le choix du binaire de sonde en tâche 7, qui est une **découverte outillée** (commande d'inspection fournie, cibles applicatives fournies, règle de repli fournie, obligation de documenter l'omission), non un blanc à remplir.

**Cohérence des noms** — `core_env_vars()` défini en tâche 3 et réutilisé en tâche 4 ; `SLOT_NAME`/`slot_is_active` définis en tâche 6, étape 3, et utilisés par le test de l'étape 1 ; les couples `(context, dockerfile)` de la matrice (tâche 1) sont identiques à ceux lus par `build_target()` sur le compose ; les 4 noms d'images de la tâche 1 sont repris à l'identique par l'overlay en tâche 2.
