# Fiabilisation déploiement Proxmox + fraîcheur images — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les 4 items encore ouverts de
`docs/superpowers/specs/2026-09-19-fiabilisation-deploiement-proxmox-fraicheur-images-design.md`
(§1.5, §1.6, §1.7, §2) — realm Keycloak jamais réactualisé, volume CSP
root-owned, spam OTel sans profil `observability`, et images `v0.1.0`
divergentes du code source.

**Architecture:** Quatre groupes de tâches indépendants, chacun livrable et
testable seul (pas d'ordre imposé entre groupes, un ordre existe à
l'intérieur de chacun) :
- **Groupe A** (Tasks 1-2) : `install.sh` réapplique les `redirectUris`
  Keycloak à chaque lancement via `kcadm.sh update`, idempotent.
- **Groupe B** (Tasks 3-4) : un service d'init Compose à usage unique fixe
  la propriété du volume `csp-dynamic-conf` avant que `worker` ne démarre.
- **Groupe C** (Tasks 5-6) : `OTEL_EXPORTER_OTLP_ENDPOINT` n'est positionné
  que si le profil `observability` est actif.
- **Groupe D** (Tasks 7-11) : la matrice de build des 9 images devient un
  workflow réutilisable, appelé par `release.yml` (tag → `v0.1.0`+`latest`,
  scans activés) et un nouveau `publish-edge.yml` (merge `dev`/`main` →
  `edge`, pas de scans), plus une porte qui vérifie que les 9 images
  existent réellement sur le registre sous le tag publié.

**Tech Stack:** Bash (`scripts/install.sh`), Docker Compose Spec (YAML),
GitHub Actions (YAML), Python 3.12/pytest/uv (`core/`).

## Global Constraints

- Toute modification de `scripts/install.sh` doit rester compatible avec le
  harnais de test existant (`core/tests/test_install_script.py` — fausses
  commandes `docker`/`jq` sur `$PATH`, jamais de vrai Docker/Keycloak).
- Aucune commande destructive (`docker volume rm`, `git push --force`, etc.)
  sans confirmation explicite de l'utilisateur.
- Conventional commits (`fix(deploy): …`, `feat(ci): …`), petits, un sujet
  — cf. CLAUDE.md.
- Toute image tierce republiée doit rester épinglée par un tag exact,
  jamais `:latest` nu dans un fichier de service (règle déjà en place,
  vérifiée par `core/tests/test_deployability.py`).
- `uv run pytest` (dans `core/`) doit rester entièrement vert après chaque
  tâche.

---

## Groupe A — Rafraîchir les `redirectUris` Keycloak à chaque lancement (§1.5)

### Task 1: Test — `install.sh` republie les redirectUris à chaque lancement

**Files:**
- Modify: `core/tests/test_install_script.py`

**Interfaces:**
- Consomme : le harnais existant (`_FAKE_DOCKER`, `_FAKE_JQ`,
  `install_workdir`, `fake_bin_path`, `_run_install`) — inchangés dans
  leur signature.
- Ne produit rien de nouveau pour d'autres tâches (test terminal).

- [ ] **Step 1: Étendre `_FAKE_DOCKER` pour distinguer `get clients` de `get users`**

Dans `core/tests/test_install_script.py`, remplacer le bloc `get)` existant
(à l'intérieur de `if [ "$service" = "keycloak" ]; then ... case "$sub" in`)
par une version qui répond différemment selon la ressource demandée (`$3`,
c'est-à-dire `clients` ou `users`) :

```sh
          get)
            resource="$3"
            if [ "$resource" = "clients" ]; then
              echo "[{\"id\":\"shell-client-fake-id\"}]"
            elif grep -q "kcadm.sh create users" "$FAKE_BIN_LOG" 2>/dev/null; then
              echo "[{\"id\":\"created-fake-id\"}]"
            elif [ -n "${FAKE_KC_EXISTING_USER_ID:-}" ]; then
              echo "[{\"id\":\"${FAKE_KC_EXISTING_USER_ID}\"}]"
            else
              echo "[]"
            fi
            exit 0
            ;;
```

(Le reste de `_FAKE_DOCKER` — cas `config`, `create`, `*)` — ne change pas ;
`update` tombe déjà dans le `*)  exit 0 ;;` catch-all existant, et le log
`echo "docker $*" >> "$FAKE_BIN_LOG"` en tête de fichier capture déjà
n'importe quel appel, y compris `update`.)

- [ ] **Step 2: Écrire le test qui échoue**

Ajouter à la fin de `core/tests/test_install_script.py` :

```python
def test_install_refreshes_the_shell_client_redirect_uris_every_run(
    install_workdir, fake_bin_path
):
    """§1.5 de la spec 2026-09-19 : le realm Keycloak n'est importé qu'une
    seule fois par Keycloak lui-même (`--import-realm` n'écrase jamais un
    realm déjà existant, vérifié empiriquement en session) — si le tout
    premier import s'est produit avec un GEOSTUDIO_PUBLIC_HOST différent
    (vide, ancien domaine...), les redirectUris restent périmés pour
    toujours sans ce correctif. install.sh doit donc les réappliquer via
    `kcadm.sh update` à CHAQUE lancement, pas seulement à la création."""
    result, log = _run_install(install_workdir, fake_bin_path)

    assert result.returncode == 0, result.stderr
    assert "get clients -r geostudio -q clientId=geostudio-shell" in log
    assert (
        'update clients/shell-client-fake-id -r geostudio '
        '-s redirectUris=["https://geostudio-test.example/",'
        '"https://geostudio-test.example/*"] -s webOrigins=["+"]'
    ) in log


def test_install_refreshes_redirect_uris_even_when_admin_account_already_exists(
    install_workdir, fake_bin_path
):
    """Le rafraîchissement ne doit pas dépendre de la branche "création de
    compte" de prompt_admin — il doit aussi jouer quand le compte admin
    existe déjà (relance normale d'un déploiement stable)."""
    result, log = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"FAKE_KC_EXISTING_USER_ID": "existing-user-42"},
    )

    assert result.returncode == 0, result.stderr
    assert (
        'update clients/shell-client-fake-id -r geostudio '
        '-s redirectUris=["https://geostudio-test.example/",'
        '"https://geostudio-test.example/*"] -s webOrigins=["+"]'
    ) in log
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_install_script.py -k redirect_uris -v`
Expected: FAIL — `'get clients -r geostudio...' in log` est faux (install.sh
n'appelle pas encore `get clients`).

- [ ] **Step 4: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_install_script.py
git commit -m "test(deploy): couvre le rafraîchissement des redirectUris Keycloak à chaque lancement"
```

### Task 2: Implémentation — `install.sh` republie les redirectUris

**Files:**
- Modify: `scripts/install.sh` (fonction `prompt_admin`)

**Interfaces:**
- Consomme : `$kc` (chemin de `kcadm.sh`, déjà défini dans `prompt_admin`),
  `$COMPOSE`, `$PUBLIC_HOST` (global, déjà posé par `prompt_public_host`
  avant l'appel à `prompt_admin`).
- Ne produit rien de nouveau.

- [ ] **Step 1: Ajouter l'appel `kcadm.sh update` juste après l'authentification réussie**

Dans `scripts/install.sh`, dans `prompt_admin()`, insérer le bloc suivant
juste après le `if [ "$authenticated" != true ]; then ... fi` (donc avant
la ligne `local admin_temp_password`) :

```bash
  echo "Synchronisation des URLs de redirection OIDC (idempotent, à chaque lancement)..."
  # Keycloak n'importe un realm que s'il n'existe pas déjà en base
  # (--import-realm n'écrase jamais un realm existant, vérifié
  # empiriquement) : le fichier realm régénéré par ce script à chaque
  # lancement (cf. `sed` plus haut sur GEOSTUDIO_PUBLIC_HOST) n'est donc
  # JAMAIS relu après le tout premier boot. Si ce premier import s'est
  # produit avec un hôte différent (vide, ancien domaine), les
  # redirectUris du client restent périmés pour toujours sans ce
  # correctif — réappliqué ici via l'API admin à chaque lancement.
  local shell_client_id
  shell_client_id="$($COMPOSE exec -T keycloak "$kc" get clients -r geostudio \
      -q clientId=geostudio-shell --fields id 2>/dev/null \
    | jq -r '.[0].id')"
  $COMPOSE exec -T keycloak "$kc" update "clients/${shell_client_id}" -r geostudio \
    -s "redirectUris=[\"https://${PUBLIC_HOST}/\",\"https://${PUBLIC_HOST}/*\"]" \
    -s "webOrigins=[\"+\"]" \
    >/dev/null

```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_install_script.py -v`
Expected: PASS (tous, y compris les deux nouveaux et les 7 pré-existants —
vérifier qu'aucun n'a régressé, notamment
`test_install_creates_an_admin_account_and_writes_core_admin_subs` qui
partage le même fake `get`).

- [ ] **Step 3: Vérifier `bash -n` (syntaxe) et commit**

```bash
bash -n scripts/install.sh
git add scripts/install.sh
git commit -m "fix(deploy): réapplique les redirectUris Keycloak à chaque lancement d'install.sh"
```

---

## Groupe B — Propriété du volume `csp-dynamic-conf` (§1.6)

### Task 3: Test — un service d'init fixe la propriété du volume avant `worker`

**Files:**
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consomme : `services(BASE)`, `load_yaml(BASE)` (helpers déjà définis en
  haut du fichier, inchangés).
- Ne produit rien de nouveau.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `core/tests/test_deployability.py`, juste après
`test_csp_dynamic_conf_volume_is_shared_between_worker_and_traefik` (déjà
présent) :

```python
def test_csp_dynamic_conf_has_an_ownership_init_service():
    """Un volume Docker nommé est peuplé (et donc son propriétaire fixé) par
    le PREMIER conteneur qui l'utilise — traefik (root) ou worker (uid
    1001, cf. core/Dockerfile) selon lequel démarre en premier, un ordre
    non déterministe. Constaté en déploiement réel : traefik a gagné la
    course, `worker` ne pouvait plus écrire
    (`PermissionError: [Errno 13] Permission denied`) et la CSP dynamique
    ne s'est jamais mise à jour. Un service d'init dédié, dont `worker`
    dépend avec `service_completed_successfully`, élimine la course."""
    base = load_yaml(BASE)
    init = base["services"].get("csp-dynamic-conf-init")
    assert init is not None, (
        "docker-compose.yml doit déclarer un service "
        "`csp-dynamic-conf-init` qui chown le volume avant `worker`"
    )
    assert any("csp-dynamic-conf" in v for v in (init.get("volumes") or [])), (
        f"csp-dynamic-conf-init doit monter csp-dynamic-conf, a trouvé : {init.get('volumes')}"
    )
    assert init.get("restart") in (None, "no"), (
        "csp-dynamic-conf-init doit s'exécuter une seule fois et sortir "
        f"(restart: {init.get('restart')!r} le ferait boucler)"
    )

    worker_depends_on = services(BASE)["worker"].get("depends_on") or {}
    init_dep = worker_depends_on.get("csp-dynamic-conf-init")
    assert init_dep is not None, (
        "worker doit dépendre de csp-dynamic-conf-init dans docker-compose.yml"
    )
    assert init_dep.get("condition") == "service_completed_successfully", (
        f"worker.depends_on.csp-dynamic-conf-init.condition = {init_dep.get('condition')!r}, "
        "attendu 'service_completed_successfully'"
    )
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_deployability.py -k csp_dynamic_conf_has_an_ownership -v`
Expected: FAIL — `init is not None` échoue (le service n'existe pas encore).

- [ ] **Step 3: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_deployability.py
git commit -m "test(deploy): couvre la propriété du volume csp-dynamic-conf via un service d'init"
```

### Task 4: Implémentation — service d'init + dépendance de `worker`

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Ne consomme ni ne produit d'interface programmatique — modification de
  configuration déclarative pure.

- [ ] **Step 1: Ajouter le service d'init**

Dans `docker-compose.yml`, juste avant la section `# ─── Auth ───` (donc
avant le service `keycloak`, à proximité de son principal consommateur
`worker` un peu plus bas — l'emplacement exact dans le fichier n'a pas
d'importance pour Compose, choisi ici pour la lisibilité), ajouter :

```yaml
  # ─── Init ──────────────────────────────────────────────

  csp-dynamic-conf-init:
    # SP-48/GAP-72, corrigé après un déploiement réel : un volume Docker
    # nommé est peuplé (propriétaire fixé) par le PREMIER conteneur qui
    # l'utilise. Sans ce service, `traefik` (root) ou `worker` (uid 1001)
    # peut gagner la course au premier démarrage, non déterministe — si
    # `traefik` gagne, `worker` ne peut plus jamais écrire la CSP
    # dynamique (`PermissionError: Permission denied`, constaté en
    # session). `worker` (ci-dessous) attend explicitement la fin de ce
    # service avant de démarrer, ce qui fixe la propriété une fois pour
    # toutes avant que quiconque d'autre ne touche au volume.
    image: busybox:1.36
    command: ["chown", "1001:1001", "/csp-dynamic"]
    volumes:
      - csp-dynamic-conf:/csp-dynamic
    networks: [gis-net]

```

- [ ] **Step 2: Faire dépendre `worker` de ce service**

Dans `docker-compose.yml`, dans le service `worker`, le bloc `depends_on`
actuel est :

```yaml
    depends_on:
      pgbouncer:
        condition: service_started
      minio:
        condition: service_started
```

Le remplacer par :

```yaml
    depends_on:
      pgbouncer:
        condition: service_started
      minio:
        condition: service_started
      csp-dynamic-conf-init:
        condition: service_completed_successfully
```

- [ ] **Step 3: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_deployability.py -k csp_dynamic_conf -v`
Expected: PASS (les 4 tests `csp_dynamic_conf*`, l'ancien et les 3 déjà
présents inclus).

- [ ] **Step 4: Vérifier que Compose accepte la syntaxe (schéma réel, pas seulement le test Python)**

Run (depuis la racine du dépôt, un `.env` minimal suffit — `cp .env.example .env`
si absent) : `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet`
Expected: aucune erreur (sortie vide, code de sortie 0). Si Docker n'est
pas disponible dans cet environnement d'exécution, documenter ce point
dans le rapport de tâche plutôt que de sauter la vérification
silencieusement — elle doit être rejouée avant fusion.

- [ ] **Step 5: Lancer la suite complète de `test_deployability.py` et commit**

```bash
cd core && uv run pytest tests/test_deployability.py -v
git add docker-compose.yml
git commit -m "fix(deploy): fixe la propriété de csp-dynamic-conf via un service d'init dédié"
```

---

## Groupe C — Ne pas exporter OTel sans le profil `observability` (§1.7)

### Task 5: Test — `install.sh` positionne `OTEL_EXPORTER_OTLP_ENDPOINT` selon le profil

**Files:**
- Modify: `core/tests/test_install_script.py`

**Interfaces:**
- Consomme : `_run_install`, `install_workdir`, `fake_bin_path` (harnais
  existant, inchangé).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_install_script.py` :

```python
def test_install_enables_otel_export_when_observability_profile_is_selected(
    install_workdir, fake_bin_path
):
    """§1.7 de la spec 2026-09-19 : core/worker/cdc-worker exportent vers
    otel-lgtm inconditionnellement dans docker-compose.yml. Sans le profil
    `observability` démarré, ça boucle en échec réseau indéfiniment
    (`Failed to resolve 'otel-lgtm'`, constaté en session, plusieurs
    lignes de log par minute). install.sh doit positionner l'endpoint
    seulement quand ce profil est sélectionné."""
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={
            "INSTALL_PROFILES": "observability",
            "FAKE_COMPOSE_PROFILES": "observability\netl",
        },
    )

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-lgtm:4318" in env_lines


def test_install_disables_otel_export_when_observability_profile_is_not_selected(
    install_workdir, fake_bin_path
):
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={
            "INSTALL_PROFILES": "",
            "FAKE_COMPOSE_PROFILES": "observability\netl",
        },
    )

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=" in env_lines
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-lgtm:4318" not in env_lines
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_install_script.py -k otel_export -v`
Expected: FAIL — `set_env_var` n'est jamais appelé pour cette variable
(absente de `.env`/`.env.example`, donc absente aussi de `.env` copié dans
`install_workdir` par la fixture), l'assertion `in env_lines` échoue.

- [ ] **Step 3: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_install_script.py
git commit -m "test(deploy): couvre l'activation conditionnelle de l'export OTel selon le profil observability"
```

### Task 6: Implémentation — `.env.example`, `install.sh`, `docker-compose.yml`

**Files:**
- Modify: `.env.example`
- Modify: `scripts/install.sh` (fonction `prompt_profiles`)
- Modify: `docker-compose.yml` (3 occurrences : `core`, `worker`, `cdc-worker`)

**Interfaces:**
- Consomme : `SELECTED_PROFILES` (tableau global déjà rempli par
  `prompt_profiles`), `set_env_var` (fonction déjà définie).

- [ ] **Step 1: Ajouter la ligne dans `.env.example`**

Dans `.env.example`, juste après la ligne `GRAFANA_ALERT_WEBHOOK_URL=` (fin
de la section `# ─── Observabilité …`), ajouter :

```
# Endpoint OTLP HTTP pour les traces/métriques de core/worker/cdc-worker.
# Positionné automatiquement par l'installeur guidé (scripts/install.sh)
# quand le profil compose `observability` est activé — vide sinon, sinon
# ces trois services retentent l'export en boucle contre un hôte qui
# n'existe pas (`otel-lgtm`), constaté en déploiement réel (bruit de log
# permanent, aucune requête applicative affectée mais gêne réelle au
# diagnostic).
OTEL_EXPORTER_OTLP_ENDPOINT=
```

- [ ] **Step 2: Rendre les 3 occurrences dans `docker-compose.yml` conditionnelles**

Dans `docker-compose.yml`, remplacer les 3 occurrences de
`OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318` (services `core`,
`worker`, `cdc-worker`) par :

```yaml
      OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_EXPORTER_OTLP_ENDPOINT:-}
```

(Chaque occurrence garde sa ligne `OTEL_SERVICE_NAME: geostudio-<service>`
juste après, inchangée.)

- [ ] **Step 3: Positionner la variable dans `install.sh` selon le profil sélectionné**

Dans `scripts/install.sh`, juste après l'appel `prompt_profiles` (ligne
`prompt_profiles` seule, avant `ensure_env_file`)  — non : `set_env_var`
n'existe et n'est utilisable qu'après `ensure_env_file` (qui crée `.env`).
Ajouter donc la nouvelle logique **après** l'appel à `ensure_env_file`,
par exemple juste après la définition de `set_env_var` et l'appel
`ensure_env_file` qui la suit :

```bash
ensure_env_file

configure_otel_export() {
  local enabled=false
  for p in "${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"}"; do
    [ "$p" = "observability" ] && enabled=true
  done
  if [ "$enabled" = true ]; then
    set_env_var OTEL_EXPORTER_OTLP_ENDPOINT "http://otel-lgtm:4318"
  else
    set_env_var OTEL_EXPORTER_OTLP_ENDPOINT ""
  fi
}

configure_otel_export

```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_install_script.py -v`
Expected: PASS (tous, y compris
`test_install_selects_profiles_and_launches_the_stack_with_them` — ne pas
régresser ce test pré-existant).

- [ ] **Step 5: Vérifier `bash -n` et commit**

```bash
bash -n scripts/install.sh
git add .env.example scripts/install.sh docker-compose.yml
git commit -m "fix(deploy): n'exporte OTel que si le profil observability est actif"
```

---

## Groupe D — Fraîcheur des images publiées (§2)

### Task 7: Test — extraction du workflow réutilisable `_build-and-push.yml`

**Files:**
- Create: `.github/workflows/_build-and-push.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Produit : la constante `BUILD_AND_PUSH` (chemin vers
  `.github/workflows/_build-and-push.yml`), consommée par
  `release_matrix()` (modifiée dans cette tâche) et par la Task 12
  (`check_published_images.py`, qui lira le même fichier indépendamment).

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_deployability.py`, ajouter la constante et le test.
D'abord, juste après la ligne `PROD = REPO / "docker-compose.prod.yml"` :

```python
BUILD_AND_PUSH = REPO / ".github/workflows/_build-and-push.yml"
```

Puis, n'importe où après la définition de `release_matrix()` :

```python
def test_build_and_push_matrix_lives_in_the_reusable_workflow():
    """§2 de la spec 2026-09-19 : la matrice des 9 images doit vivre dans un
    SEUL fichier (`_build-and-push.yml`, réutilisable par `release.yml` ET
    par le futur `publish-edge.yml`) — jamais recopiée, sous peine de
    dériver silencieusement entre les deux (classe de bug déjà payée sur ce
    dépôt, cf. CLAUDE.md piège n°2)."""
    assert BUILD_AND_PUSH.exists(), (
        "attendu : .github/workflows/_build-and-push.yml (workflow réutilisable)"
    )
    doc = yaml.safe_load(BUILD_AND_PUSH.read_text())
    # PyYAML résout la clé `on:` non quotée en booléen `True` (YAML 1.1),
    # pas en chaîne "on" — vérifié empiriquement contre release.yml réel
    # (`list(doc.keys())` donne `['name', True, 'jobs']`).
    assert "workflow_call" in doc[True], (
        "_build-and-push.yml doit être déclenchable via `on: workflow_call`"
    )
    matrix = doc["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]
    images = {e["image"] for e in matrix}
    assert images == {
        "geostudio-core",
        "geostudio-shell",
        "geostudio-postgis",
        "geostudio-titiler",
        "geostudio-appexport-standalone",
        "geostudio-export-worker",
        "geostudio-qgis-worker",
        "geostudio-appexport-runtime-builder",
        "geostudio-backup",
    }, f"matrice inattendue : {images}"


def test_release_yml_calls_the_reusable_build_workflow():
    """release.yml ne doit plus déclarer la matrice en dur — seulement
    appeler le workflow réutilisable, avec les deux tags historiques
    (le tag poussé + `latest`) et les scans activés."""
    doc = yaml.safe_load(RELEASE.read_text())
    job = doc["jobs"]["build-and-push"]
    assert job.get("uses") == "./.github/workflows/_build-and-push.yml", (
        f"release.yml build-and-push.uses = {job.get('uses')!r}, "
        "attendu './.github/workflows/_build-and-push.yml'"
    )
    assert job["needs"] == ["test-gate", "test-gate-arm64"] or set(job["needs"]) == {
        "test-gate",
        "test-gate-arm64",
    }
    with_inputs = job["with"]
    assert with_inputs["also_tag_latest"] is True
    assert with_inputs["run_scans"] is True
```

Mettre à jour `release_matrix()` (déjà définie plus haut dans le fichier)
pour lire depuis le nouveau fichier :

```python
def release_matrix() -> list[dict]:
    return load_yaml(BUILD_AND_PUSH)["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]
```

(`RELEASE` reste utilisé tel quel par les tests portant sur `test-gate` /
`test-gate-arm64`, qui restent dans `release.yml` — ne pas y toucher.)

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_deployability.py -k "build_and_push_matrix or release_yml_calls" -v`
Expected: FAIL — `_build-and-push.yml` n'existe pas encore
(`BUILD_AND_PUSH.exists()` est faux), et par ricochet tous les tests qui
appellent `release_matrix()` échouent aussi tant que le fichier n'existe
pas (attendu, à corriger dans les steps suivants du même commit logique).

- [ ] **Step 3: Créer `.github/workflows/_build-and-push.yml`**

Contenu complet (matrice recopiée à l'identique depuis l'actuel
`release.yml`, paramétrée par `inputs.image_tag`/`also_tag_latest`/`run_scans`) :

```yaml
name: Build and push images (reusable)

on:
  workflow_call:
    inputs:
      image_tag:
        description: "Tag principal à publier (ex. v0.1.0, ou edge)"
        required: true
        type: string
      also_tag_latest:
        description: "Publier aussi sous :latest (réservé aux vraies releases)"
        required: false
        type: boolean
        default: false
      run_scans:
        description: "Exécuter Trivy + SBOM (coûteux, réservé aux vraies releases)"
        required: false
        type: boolean
        default: false

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      security-events: write
    strategy:
      # Sans ceci, un échec sur une seule des neuf legs (par ex. disque ou
      # timeout sur geostudio-qgis-worker, 11.1 Go, ou geostudio-export-worker,
      # 3.14 Go) annule les huit autres avant publication — dont core/shell/
      # postgis, qui n'ont eux-mêmes aucune raison d'échouer.
      fail-fast: false
      matrix:
        include:
          - image: geostudio-core
            context: ./core
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-shell
            context: ./shell
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-postgis
            context: ./deploy/postgis
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-titiler
            context: ./deploy/titiler
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-appexport-standalone
            context: .
            dockerfile: deploy/appexport-standalone/Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-export-worker
            context: ./core
            dockerfile: ../deploy/export-worker/Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-qgis-worker
            context: ./deploy/qgis-worker
            dockerfile: Dockerfile
            # Base qgis/qgis:release-3_34 mono-arch (probable amd64 seul),
            # image 11 Go — hors périmètre du portage arm64.
            platforms: linux/amd64
          - image: geostudio-appexport-runtime-builder
            context: .
            dockerfile: deploy/appexport-runtime-builder/Dockerfile
            platforms: linux/amd64,linux/arm64
          - image: geostudio-backup
            context: ./deploy/backup
            dockerfile: Dockerfile
            platforms: linux/amd64,linux/arm64
    steps:
      - uses: actions/checkout@v7

      - uses: docker/setup-qemu-action@v4

      - uses: docker/setup-buildx-action@v4

      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Compute tags
        id: tags
        shell: bash
        run: |
          tags="ghcr.io/tlenenao/${{ matrix.image }}:${{ inputs.image_tag }}"
          if [ "${{ inputs.also_tag_latest }}" = "true" ]; then
            tags="${tags}
          ghcr.io/tlenenao/${{ matrix.image }}:latest"
          fi
          {
            echo "tags<<GEOSTUDIO_TAGS_EOF"
            echo "$tags"
            echo "GEOSTUDIO_TAGS_EOF"
          } >> "$GITHUB_OUTPUT"

      - uses: docker/build-push-action@v7
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.context }}/${{ matrix.dockerfile }}
          platforms: ${{ matrix.platforms }}
          push: true
          tags: ${{ steps.tags.outputs.tags }}

      # Report-only : exit-code 0 quel que soit le résultat, ce scan ne
      # bloque jamais la publication. Réservé aux vraies releases
      # (run_scans) — coûteux à répéter sur les 9 images à chaque merge
      # dev/main, alors qu'un tag `edge` est déjà remplacé au merge suivant.
      - name: Trivy (report-only)
        if: inputs.run_scans
        continue-on-error: true
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ghcr.io/tlenenao/${{ matrix.image }}:${{ inputs.image_tag }}
          format: sarif
          output: trivy-${{ matrix.image }}.sarif
          severity: CRITICAL,HIGH
          exit-code: "0"

      - name: Upload Trivy results
        if: inputs.run_scans && hashFiles(format('trivy-{0}.sarif', matrix.image)) != ''
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: trivy-${{ matrix.image }}.sarif
          category: trivy-${{ matrix.image }}

      - name: SBOM
        if: inputs.run_scans
        continue-on-error: true
        uses: anchore/sbom-action@v0.24.0
        with:
          image: ghcr.io/tlenenao/${{ matrix.image }}:${{ inputs.image_tag }}
          artifact-name: ${{ matrix.image }}-sbom.spdx.json
          output-file: ${{ matrix.image }}-sbom.spdx.json
```

- [ ] **Step 4: Remplacer le job `build-and-push` de `release.yml` par un appel**

Dans `.github/workflows/release.yml`, remplacer l'intégralité du job
`build-and-push:` (de `build-and-push:` jusqu'à la fin du fichier, c'est-à-
-dire tout ce qui suit `needs: [test-gate, test-gate-arm64]` — `runs-on`,
`permissions`, `strategy`, `steps`) par :

```yaml
  build-and-push:
    needs: [test-gate, test-gate-arm64]
    uses: ./.github/workflows/_build-and-push.yml
    permissions:
      contents: read
      packages: write
      security-events: write
    with:
      image_tag: ${{ github.ref_name }}
      also_tag_latest: true
      run_scans: true
    secrets: inherit
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS (l'intégralité du fichier — vérifier en particulier
`test_release_matrix_declares_multiarch_platforms_except_qgis_worker`,
`test_every_build_service_has_a_released_image`,
`test_every_referenced_ghcr_image_is_released`,
`test_build_and_push_needs_both_test_gates`, qui dépendent toutes de
`release_matrix()`/`RELEASE` et ne doivent pas régresser).

- [ ] **Step 6: Valider la syntaxe YAML réelle et commit**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/_build-and-push.yml')); yaml.safe_load(open('.github/workflows/release.yml'))"
cd core && uv run pytest tests/test_deployability.py -v
git add .github/workflows/_build-and-push.yml .github/workflows/release.yml core/tests/test_deployability.py
git commit -m "refactor(ci): extrait la matrice des 9 images en workflow réutilisable"
```

### Task 8: Test — `check_published_images.py` détecte une image absente du registre

**Files:**
- Create: `core/scripts/check_published_images.py`
- Create: `core/tests/test_check_published_images.py`

**Interfaces:**
- Produit : `release_images() -> list[str]`, `check_all(images: list[str], tag: str, *, checker: Callable[[str, str], bool] = image_exists) -> list[str]`,
  `image_exists(image: str, tag: str) -> bool` — noms et signatures
  consommés tels quels par Task 9 (câblage CI) et par la Task 7 (aucune
  dépendance inverse, juste listé pour cohérence).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `core/tests/test_check_published_images.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""§2 de la spec 2026-09-19 : porte de complétude — un job release.yml
pouvait déclarer une image dans sa matrice sans jamais réellement la
publier (geostudio-titiler, trouvé en déploiement réel : 404 anonyme sur
GHCR, pas un problème de visibilité). `test_deployability.py` compare déjà
compose ↔ matrice déclarée, mais jamais matrice déclarée ↔ registre réel
— c'est ce que ce script comble, à exécuter en CI après chaque publication."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.check_published_images import check_all, release_images  # noqa: E402


def test_release_images_lists_the_nine_matrix_images():
    images = release_images()
    assert images == [
        "geostudio-core",
        "geostudio-shell",
        "geostudio-postgis",
        "geostudio-titiler",
        "geostudio-appexport-standalone",
        "geostudio-export-worker",
        "geostudio-qgis-worker",
        "geostudio-appexport-runtime-builder",
        "geostudio-backup",
    ]


def test_check_all_reports_missing_images():
    def fake_checker(image: str, tag: str) -> bool:
        return image != "geostudio-titiler"

    missing = check_all(
        ["geostudio-core", "geostudio-titiler", "geostudio-shell"],
        "edge",
        checker=fake_checker,
    )

    assert missing == ["geostudio-titiler"]


def test_check_all_reports_nothing_when_everything_is_published():
    missing = check_all(["geostudio-core"], "edge", checker=lambda image, tag: True)

    assert missing == []
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_check_published_images.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.check_published_images'`.

- [ ] **Step 3: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_check_published_images.py
git commit -m "test(ci): couvre la porte de complétude des images publiées"
```

### Task 9: Implémentation — `check_published_images.py`

**Files:**
- Create: `core/scripts/check_published_images.py`

**Interfaces:**
- Implémente exactement les signatures listées dans l'interface de la
  Task 8 : `release_images() -> list[str]`,
  `image_exists(image: str, tag: str) -> bool`,
  `check_all(images: list[str], tag: str, *, checker=image_exists) -> list[str]`,
  `main() -> int`.

- [ ] **Step 1: Écrire l'implémentation**

Créer `core/scripts/check_published_images.py` :

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Vérifie que toutes les images de la matrice `_build-and-push.yml`
existent réellement sur GHCR sous un tag donné — cf.
core/tests/test_check_published_images.py pour le contexte (geostudio-
titiler, déclaré dans la matrice mais jamais publié, trouvé en
déploiement réel). Requête anonyme au registre (le token d'échange OAuth2
de Docker Distribution ne nécessite aucune authentification pour un
package public) : aucun secret requis pour exécuter ce script."""

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BUILD_AND_PUSH = REPO / ".github/workflows/_build-and-push.yml"
OWNER = "tlenenao"


def release_images() -> list[str]:
    doc = yaml.safe_load(BUILD_AND_PUSH.read_text())
    matrix = doc["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]
    return [entry["image"] for entry in matrix]


def _fetch_token(image: str) -> str:
    url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{OWNER}/{image}:pull"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.load(resp)["token"]


def image_exists(image: str, tag: str) -> bool:
    try:
        token = _fetch_token(image)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError):
        return False
    request = urllib.request.Request(  # noqa: S310
        f"https://ghcr.io/v2/{OWNER}/{image}/manifests/{tag}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json",
        },
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        return False


def check_all(images: list[str], tag: str, *, checker=image_exists) -> list[str]:
    return [image for image in images if not checker(image, tag)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Tag à vérifier sur ghcr.io/tlenenao/<image>")
    args = parser.parse_args()

    images = release_images()
    missing = check_all(images, args.tag)

    if missing:
        print(
            f"✗ {len(missing)}/{len(images)} image(s) absente(s) sous le tag "
            f"'{args.tag}' : {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    print(f"✓ Les {len(images)} images existent sous le tag '{args.tag}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_check_published_images.py -v`
Expected: PASS (3 tests).

- [ ] **Step 3: Vérifier que `pyyaml` est bien une dépendance résolue (déjà utilisée par test_deployability.py)**

Run: `cd core && uv run python -c "import yaml; print('ok')"`
Expected: `ok` (si ça échoue, `pyyaml` manque au groupe de dépendances de
test — l'ajouter dans `core/pyproject.toml` au même groupe que ce qui
fournit déjà `yaml` à `test_deployability.py` avant de continuer).

- [ ] **Step 4: `ruff check`/`ruff format` et commit**

```bash
cd core
uv run ruff check scripts/check_published_images.py tests/test_check_published_images.py
uv run ruff format --check scripts/check_published_images.py tests/test_check_published_images.py
git add core/scripts/check_published_images.py
git commit -m "feat(ci): script de vérification que les images publiées existent réellement"
```

### Task 10: `publish-edge.yml` — rebuild sur merge dev/main, tag `edge`

**Files:**
- Create: `.github/workflows/publish-edge.yml`
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consomme : `.github/workflows/_build-and-push.yml` (Task 7),
  `core/scripts/check_published_images.py` (Task 9).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_deployability.py` :

```python
PUBLISH_EDGE = REPO / ".github/workflows/publish-edge.yml"


def test_publish_edge_triggers_on_merge_not_on_every_ci_run():
    """Rebuild sur CHAQUE exécution de CI (chaque push, chaque PR) inonderait
    le registre d'images pour des commits jamais mergés — vérifié contre
    `release.yml` réel que rien de tel n'existe aujourd'hui (déclenché
    seulement par `push: tags:`, jamais par `branches:`), ce qui a
    précisément laissé geostudio-titiler sans jamais être construit.
    Décision actée (spec §2.3) : un tag `edge` reconstruit sur MERGE vers
    dev/main, pas sur chaque CI."""
    assert PUBLISH_EDGE.exists(), "attendu : .github/workflows/publish-edge.yml"
    doc = yaml.safe_load(PUBLISH_EDGE.read_text())
    # PyYAML résout la clé `on:` non quotée en booléen `True` (YAML 1.1) —
    # vérifié empiriquement contre release.yml réel, cf. commentaire de
    # test_build_and_push_matrix_lives_in_the_reusable_workflow ci-dessus.
    on = doc[True]
    branches = set(on["push"]["branches"])
    assert branches == {"dev", "main"}, f"déclencheur inattendu : {branches}"
    assert "pull_request" not in on, (
        "publish-edge.yml ne doit jamais se déclencher sur une PR — "
        "seulement sur un merge réel vers dev/main"
    )


def test_publish_edge_calls_the_reusable_workflow_with_the_edge_tag():
    doc = yaml.safe_load(PUBLISH_EDGE.read_text())
    job = doc["jobs"]["build-and-push"]
    assert job.get("uses") == "./.github/workflows/_build-and-push.yml"
    with_inputs = job["with"]
    assert with_inputs["image_tag"] == "edge"
    assert with_inputs["also_tag_latest"] is False
    assert with_inputs["run_scans"] is False


def test_publish_edge_verifies_all_images_landed():
    doc = yaml.safe_load(PUBLISH_EDGE.read_text())
    verify = doc["jobs"].get("verify-published")
    assert verify is not None, "publish-edge.yml doit avoir un job verify-published"
    assert verify["needs"] == "build-and-push" or "build-and-push" in verify["needs"]
    runs = " ".join(step.get("run", "") for step in verify["steps"])
    assert "check_published_images.py edge" in runs
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_deployability.py -k publish_edge -v`
Expected: FAIL — `publish-edge.yml` n'existe pas.

- [ ] **Step 3: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_deployability.py
git commit -m "test(ci): couvre le déclencheur et le contenu de publish-edge.yml"
```

- [ ] **Step 4: Créer `.github/workflows/publish-edge.yml`**

```yaml
name: Publish edge images

# Reconstruit les 9 images sous le tag `edge` à chaque MERGE vers dev/main
# — jamais sur chaque exécution de CI (chaque push/PR inonderait le
# registre pour des commits jamais mergés). `release.yml` reste le seul
# déclencheur de vraies releases versionnées (push d'un tag `v*.*.*`).
# Pas de re-exécution de test-gate/test-gate-arm64 ici : ci.yml a déjà
# gaté ce même commit avant que le merge n'ait lieu.
on:
  push:
    branches: [dev, main]

jobs:
  build-and-push:
    uses: ./.github/workflows/_build-and-push.yml
    permissions:
      contents: read
      packages: write
    with:
      image_tag: edge
      also_tag_latest: false
      run_scans: false
    secrets: inherit

  verify-published:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - name: Vérifie que les 9 images existent sous le tag edge
        working-directory: core
        run: |
          uv sync
          uv run python scripts/check_published_images.py edge
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS (fichier entier).

- [ ] **Step 6: Valider la syntaxe YAML et commit**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/publish-edge.yml'))"
cd core && uv run pytest tests/test_deployability.py -v
git add .github/workflows/publish-edge.yml core/tests/test_deployability.py
git commit -m "feat(ci): reconstruit les images sous le tag edge à chaque merge dev/main"
```

### Task 11: Ajouter la porte de complétude au workflow de release existant

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consomme : `core/scripts/check_published_images.py` (Task 9).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_deployability.py` :

```python
def test_release_yml_verifies_all_images_landed_under_the_pushed_tag():
    """geostudio-titiler était déclaré dans la matrice mais jamais publié
    sous v0.1.0 (404 anonyme réel sur GHCR) — aucune étape de release.yml
    ne le détectait avant ce garde-fou."""
    doc = yaml.safe_load(RELEASE.read_text())
    verify = doc["jobs"].get("verify-published")
    assert verify is not None, "release.yml doit avoir un job verify-published"
    assert verify["needs"] == "build-and-push" or "build-and-push" in verify["needs"]
    runs = " ".join(step.get("run", "") for step in verify["steps"])
    assert "check_published_images.py" in runs
    assert "github.ref_name" in runs
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_deployability.py -k release_yml_verifies -v`
Expected: FAIL — pas de job `verify-published` dans `release.yml`.

- [ ] **Step 3: Commit du test (rouge, attendu)**

```bash
git add core/tests/test_deployability.py
git commit -m "test(ci): couvre la porte de complétude sur release.yml"
```

- [ ] **Step 4: Ajouter le job à `release.yml`**

Dans `.github/workflows/release.yml`, à la fin du fichier (après le job
`build-and-push` remplacé en Task 7), ajouter :

```yaml

  verify-published:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - name: Vérifie que les 9 images existent sous ce tag
        working-directory: core
        run: |
          uv sync
          uv run python scripts/check_published_images.py "${{ github.ref_name }}"
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS (fichier entier — dernière vérification de ce groupe).

- [ ] **Step 6: Valider la syntaxe YAML et commit**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
cd core && uv run pytest tests/test_deployability.py -v
git add .github/workflows/release.yml core/tests/test_deployability.py
git commit -m "fix(ci): ajoute la porte de complétude des images à release.yml"
```

---

## Fin de plan — vérifications finales

- [ ] **Suite complète** : `cd core && uv run pytest -v` entièrement vert.
- [ ] **Lint** : `cd core && uv run ruff check . && uv run ruff format --check .`
- [ ] **Import-linter** : `cd core && uv run lint-imports`
- [ ] **`bash -n scripts/install.sh`** sans erreur.
- [ ] **`git log --oneline` de la branche** : un commit de test rouge séparé
  d'un commit d'implémentation pour chaque paire de tasks (1/2, 3/4, 5/6,
  8/9, 10 et 11 chacun en 2 commits), sauf la Task 7 (test + fichiers créés
  regroupés en un seul commit — extraction, pas ajout de comportement) —
  vérifier qu'aucun commit ne mélange deux sujets indépendants.
- [ ] **Revue finale de branche** (superpowers:requesting-code-review) avant
  fusion vers `dev` — en particulier : les 3 workflows YAML
  (`_build-and-push.yml`, `release.yml`, `publish-edge.yml`) n'ont jamais
  tourné pour de vrai sur GitHub Actions dans cette session (pas d'accès),
  seule la syntaxe et la structure ont été vérifiées localement. Une
  première exécution réelle (push d'un tag de test, ou merge sur `dev`)
  reste à observer avant de faire confiance à ce pipeline pour une vraie
  release.
