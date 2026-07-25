# SP-Deploy-c — Installeur guidé universel : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `git clone` → `./scripts/install.sh` → répondre à quelques questions → URL publique en main, aussi bien pour le mainteneur que pour un tiers, avec détection/installation des prérequis (consentement explicite), un menu de profils qui reflète les capacités réellement présentes dans le dépôt, et un script idempotent (rejouable sans casse).

**Architecture:** Un script bash unique (`scripts/install.sh`), surcouche de `scripts/bootstrap-env.sh` (existant, réutilisé tel quel pour la génération des secrets), orchestrant `docker-compose.prod.yml` (SP-Deploy-a/b). Il découvre les profils compose disponibles via `docker compose config --profiles` plutôt que de les coder en dur (une capacité future livrée = une ligne de plus dans `AVAILABLE_PROFILE_LABELS`, jamais une réécriture du script). L'hôte public est soit fourni par l'utilisateur, soit **découvert automatiquement** : le script démarre le tunnel Tailscale en premier et interroge `tailscale status --json` pour son propre nom `*.ts.net`, plutôt que de demander à l'utilisateur de le deviner. Le premier administrateur est créé directement via l'API Admin REST de Keycloak (évite l'écueil « aucun compte n'existe encore tant que personne ne s'est connecté » déjà documenté pour le mode `mock` dans `2026-07-16-sp9-install-secrets.md` — en mode `oidc` réel, il n'y a pas de `mockuser` auto-promu).

**Tech Stack:** bash (`set -euo pipefail`), Docker Compose v2 (`--profiles`, déjà vérifié disponible), `curl`/`jq` (API Admin Keycloak — mêmes outils que le service `backup`, SP-Deploy-b), `openssl` (génération de mots de passe temporaires, même patron que `bootstrap-env.sh`).

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md` (§5).
- **Jamais d'installation silencieuse ni d'élévation de privilège furtive** (spec §5.1) : toute action qui installe un paquet ou modifie les groupes système (`usermod -aG docker`) est précédée d'un message explicite et d'une confirmation `y/N`.
- **`get.docker.com` est déjà distro-agnostique** (détecte lui-même apt/dnf/pacman en interne) — ce script ne réimplémente pas cette détection, il se contente de confirmer puis d'invoquer le script officiel. Simplification volontaire par rapport à la lettre de la spec §5.1 (qui évoque une détection de distro par ce script), justifiée : dupliquer une détection que l'outil officiel fait déjà romprait DRY sans bénéfice.
- **Pas de binaire tunnel à installer sur l'hôte** : le service `tunnel` (SP-Deploy-a Task 5) tourne en conteneur (`tailscale/tailscale`) — l'installeur ne vérifie/installe donc **aucun binaire `tailscale` local**, seulement la présence d'une clé `TS_AUTHKEY` valide. Écart assumé par rapport à la lettre de la spec §5.1 (« vérifie le binaire du tunnel choisi »), cohérent avec l'architecture sidecar déjà actée.
- **Menu de profils découvert, pas codé en dur** (spec §5.2) : `docker compose config --profiles` liste les profils réellement définis dans le dépôt ; `ETL no-code` (SP-15) reste affiché mais désactivé tant qu'il n'apparaît pas dans cette liste.
- **Idempotent** (spec §5.3, critère §7-6) : un second passage ne doit ni dupliquer un `.env` existant (`bootstrap-env.sh` s'en charge déjà), ni recréer un admin Keycloak déjà existant, ni casser une stack déjà démarrée.
- **Toute vérification de ce sous-plan s'exécute dans un clone jetable** (`/tmp` ou le répertoire scratchpad), **jamais dans le dépôt de travail réel** — un incident de cette même session a effacé un `.env` réel en testant une commande directement dans le dépôt (`rm -f .env` après un test mal isolé) ; ce sous-plan ne reproduit pas cette erreur : chaque Step de vérification clone d'abord (`git clone . /tmp/...`), opère dans le clone, puis le supprime.
- **En-tête** `# SPDX-License-Identifier: Apache-2.0` en première ligne (commentaire bash) de tout nouveau script.
- **Pas de suite pytest/Vitest** : c'est un script d'infrastructure interactif, vérifié en le faisant tourner réellement (mode non-interactif via variables d'environnement pré-remplies pour l'automatisation des Steps de vérification, cf. Task 1 Step 3).
- **Docs et messages en français** (le script s'adresse à un mainteneur solo francophone, cohérent avec `CLAUDE.md`), identifiants/variables en anglais.

---

### Task 1 : squelette + détection/installation des prérequis Docker

**Files:**
- Create: `scripts/install.sh`

**Interfaces:**
- Consumes: `scripts/bootstrap-env.sh` (existant, inchangé) ; `docker-compose.prod.yml` (SP-Deploy-a/b, existant).
- Produces: fonctions bash `confirm()`, `ensure_docker()` — réutilisées par toutes les tâches suivantes du même fichier.

**Contexte vérifié :** `docker compose version` (sous-commande, pas `docker-compose` legacy) est la façon correcte de tester la présence du plugin Compose v2 — vérifié sur cet environnement (`Docker Compose version v5.1.3`). `get.docker.com` est le script d'installation officiel documenté par Docker, auto-détecte apt/dnf/pacman/zypper en interne.

- [ ] **Step 1: Squelette + helpers**

Créer `scripts/install.sh` :

```bash
#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# Confirmation interactive — jamais d'action destructive/installante sans
# accord explicite (spec SP-Deploy §5.1). INSTALL_YES=1 permet un mode
# non-interactif pour les Steps de vérification de ce plan (jamais utilisé
# pour un vrai déploiement humain).
confirm() {
  if [ "${INSTALL_YES:-0}" = "1" ]; then
    echo "$1 [y/N] → y (INSTALL_YES=1)"
    return 0
  fi
  read -r -p "$1 [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

echo "═══ GeoStudio — installeur guidé ═══"
```

- [ ] **Step 2: Détection/installation de Docker**

Ajouter à `scripts/install.sh` :

```bash
ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "✓ Docker + Docker Compose détectés ($(docker compose version --short))."
    return 0
  fi

  echo "✗ Docker (avec le plugin Compose v2) est requis et n'a pas été détecté."
  case "$(uname -s)" in
    Linux)
      if confirm "Installer Docker maintenant via le script officiel get.docker.com ?"; then
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        echo "Docker installé. Déconnectez-vous/reconnectez-vous (ou lancez 'newgrp docker')"
        echo "pour que l'appartenance au groupe docker prenne effet, puis relancez ce script."
        exit 0
      fi
      echo "Installation annulée — relancez ce script une fois Docker installé manuellement."
      exit 1
      ;;
    Darwin)
      echo "macOS : installez Docker Desktop manuellement : https://www.docker.com/products/docker-desktop/"
      echo "Relancez ce script une fois Docker Desktop démarré."
      exit 1
      ;;
    *)
      echo "OS non reconnu automatiquement : installez Docker manuellement"
      echo "(https://docs.docker.com/get-docker/), puis relancez ce script."
      exit 1
      ;;
  esac
}

ensure_docker
```

- [ ] **Step 3: Vérifier réellement (cas nominal — Docker déjà présent)**

Dans un clone jetable, jamais dans le dépôt de travail :

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
chmod +x /tmp/geostudio-install-test/scripts/install.sh
cd /tmp/geostudio-install-test && ./scripts/install.sh
```

Expected : `✓ Docker + Docker Compose détectés (...)` (l'environnement d'exécution de ce plan a déjà Docker), puis le script se termine normalement (rien après `ensure_docker` pour l'instant — Task 2 continue).

```bash
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 4: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur guidé — squelette + détection Docker"
```

---

### Task 2 : menu de profils (découverte, pas codé en dur)

**Files:**
- Modify: `scripts/install.sh`

**Interfaces:**
- Consumes: `docker compose config --profiles` (sous-commande vérifiée disponible, Docker Compose v2).
- Produces: variable `SELECTED_PROFILES` (tableau bash, ex. `(observability)` ou vide) et `SEED_DEMO` (`true`/`false`) — consommées par la Task 4 (lancement).

**Contexte vérifié :** `docker compose config --profiles` sur ce dépôt liste aujourd'hui exactement `observability` (seul profil défini, `docker-compose.yml` services `otel-lgtm`/`postgres-exporter`) — confirmé en l'exécutant réellement pendant l'écriture de ce plan.

- [ ] **Step 1: Découverte + menu**

Ajouter à `scripts/install.sh` :

```bash
declare -A KNOWN_PROFILE_LABELS=(
  [observability]="Observabilité (Grafana/Loki/Tempo/Prometheus)"
  [etl]="ETL no-code (SP-15)"
)

SELECTED_PROFILES=()
SEED_DEMO=false

prompt_profiles() {
  local available
  available="$($COMPOSE config --profiles 2>/dev/null || true)"

  echo ""
  echo "── Profils disponibles ──"
  while IFS= read -r profile; do
    [ -z "$profile" ] && continue
    label="${KNOWN_PROFILE_LABELS[$profile]:-$profile}"
    if confirm "Activer : ${label} ?"; then
      SELECTED_PROFILES+=("$profile")
    fi
  done <<< "$available"

  # ETL (SP-15) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-15) — à venir, pas encore disponible dans ce dépôt)"
  fi

  echo ""
  if confirm "Charger des données de démo (collections incidents/points_interet, publiques, éditables) ?"; then
    SEED_DEMO=true
  fi
}

prompt_profiles
```

- [ ] **Step 2: Vérifier réellement (mode non-interactif)**

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
cd /tmp/geostudio-install-test
INSTALL_YES=1 ./scripts/install.sh 2>&1 | grep -A3 "Profils disponibles"
```

Expected : `Activer : Observabilité (Grafana/Loki/Tempo/Prometheus) ? [y/N] → y (INSTALL_YES=1)`, ligne `(ETL no-code (SP-15) — à venir...)` affichée (le profil `etl` n'existe pas encore dans ce dépôt), puis la question sur le seed de démo.

```bash
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 3: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur — menu de profils découverts dynamiquement"
```

---

### Task 3 : bootstrap Q&A — hôte public, `.env`, premier admin Keycloak

**Files:**
- Modify: `scripts/install.sh`

**Interfaces:**
- Consumes: `scripts/bootstrap-env.sh` (existant) ; service `tunnel` (SP-Deploy-a Task 5) ; API Admin REST Keycloak (même mécanisme d'authentification que `deploy/backup/backup.sh`, SP-Deploy-b).
- Produces: `.env` complété (`GEOSTUDIO_PUBLIC_HOST`, `TS_AUTHKEY`, `CORE_ADMIN_SUBS`, `BACKUP_*` si renseignés) — consommé par la Task 4 (lancement final).

**Contexte vérifié en lisant le code :**
- `core/scripts/seed_demo.py:36-38` : `CORE_ADMIN_SUBS` (liste de `sub` OIDC séparés par des virgules) — aucun utilisateur n'est admin tant qu'un `sub` n'y figure pas. En mode `oidc` réel (pas `mock`), il n'existe pas de `mockuser` auto-promu (`core/app/auth/dependency.py`) : sans cette étape, personne ne peut jamais devenir admin après un premier déploiement propre.
- Pour Keycloak, l'identifiant interne (`id`) d'un utilisateur créé via l'API Admin **est** la valeur du claim `sub` des tokens émis pour ce compte — créer l'utilisateur via l'API et lire son `id` donne directement la valeur à écrire dans `CORE_ADMIN_SUBS`, sans attendre une première connexion.
- `docker-compose.yml` service `keycloak` : `KEYCLOAK_ADMIN: admin` / `KEYCLOAK_ADMIN_PASSWORD: ${KC_PASSWORD}` — identifiants déjà disponibles pour l'authentification admin-cli (même flux que `deploy/backup/backup.sh`, SP-Deploy-b Task 1).
- `tailscale status --json` expose le nom MagicDNS du nœud sous `.Self.DNSName` (avec un point final) — à confirmer empiriquement à l'exécution (Step 4 de cette tâche), avant de committer si le champ diffère de ce qui est documenté ici.

- [ ] **Step 1: Génération du `.env` (réutilise `bootstrap-env.sh`)**

Ajouter à `scripts/install.sh` :

```bash
ensure_env_file() {
  if [ ! -f .env ]; then
    ./scripts/bootstrap-env.sh
  else
    echo "✓ .env existe déjà — secrets conservés (idempotent)."
  fi
}

set_env_var() {
  # $1 = nom, $2 = valeur — jamais d'écrasement d'une AUTRE variable que
  # celle ciblée (même précaution que bootstrap-env.sh : sed -i.bak, ligne
  # exacte "^NAME=", suffixe .bak supprimé immédiatement après).
  sed -i.bak "s|^${1}=.*|${1}=${2}|" .env
  rm -f .env.bak
}

ensure_env_file
```

- [ ] **Step 2: Question hôte public + clé Tailscale**

```bash
prompt_public_host() {
  echo ""
  read -r -p "Nom d'hôte public (laisser vide pour le découvrir via Tailscale Funnel) : " PUBLIC_HOST_INPUT
  # TS_AUTHKEY déjà exporté dans l'environnement (automatisation, Step 5 de
  # cette tâche) : ne pas redemander — sinon, question interactive.
  if [ -z "${TS_AUTHKEY:-}" ]; then
    read -r -p "Clé Tailscale (TS_AUTHKEY — https://login.tailscale.com/admin/settings/keys) : " TS_AUTHKEY
  fi
  set_env_var TS_AUTHKEY "$TS_AUTHKEY"

  if [ -n "$PUBLIC_HOST_INPUT" ]; then
    PUBLIC_HOST="$PUBLIC_HOST_INPUT"
    return 0
  fi

  echo "Démarrage du tunnel pour découvrir automatiquement un nom *.ts.net..."
  $COMPOSE up -d traefik tunnel
  local dns_name=""
  for _ in $(seq 1 30); do
    dns_name="$($COMPOSE exec -T tunnel tailscale status --json 2>/dev/null \
      | jq -r '.Self.DNSName // empty' | sed 's/\.$//')"
    [ -n "$dns_name" ] && break
    sleep 2
  done
  if [ -z "$dns_name" ]; then
    echo "✗ Impossible de découvrir automatiquement un nom *.ts.net (délai dépassé)." >&2
    echo "  Vérifiez TS_AUTHKEY, ou fournissez un nom d'hôte manuellement et relancez." >&2
    exit 1
  fi
  PUBLIC_HOST="$dns_name"
  echo "✓ Hôte découvert : ${PUBLIC_HOST}"
}

prompt_public_host
set_env_var GEOSTUDIO_PUBLIC_HOST "$PUBLIC_HOST"
```

- [ ] **Step 3: Activation du Funnel + question cible de sauvegarde**

```bash
activate_funnel() {
  echo "Activation de Tailscale Funnel (accès public sans port ouvert)..."
  $COMPOSE exec -T tunnel tailscale funnel --bg 80
}

prompt_backup_target() {
  echo ""
  read -r -p "Cible de sauvegarde hors-site (endpoint S3-compatible, optionnel — Entrée pour ignorer) : " s3_endpoint
  if [ -n "$s3_endpoint" ]; then
    read -r -p "  Access key : " s3_access
    read -r -p "  Secret key : " s3_secret
    read -r -p "  Bucket [geostudio-backups] : " s3_bucket
    set_env_var BACKUP_S3_ENDPOINT "$s3_endpoint"
    set_env_var BACKUP_S3_ACCESS_KEY "$s3_access"
    set_env_var BACKUP_S3_SECRET_KEY "$s3_secret"
    set_env_var BACKUP_S3_BUCKET "${s3_bucket:-geostudio-backups}"
    echo "  Rappel : générez une paire de clés age (age-keygen) et renseignez la clé"
    echo "  PUBLIQUE dans BACKUP_AGE_RECIPIENT — gardez la clé privée hors de cette machine."
  else
    echo "  Aucune cible hors-site — les sauvegardes resteront locales (avertissement du service backup à chaque exécution)."
  fi
}

activate_funnel
prompt_backup_target
```

- [ ] **Step 4: Création du premier administrateur Keycloak**

```bash
prompt_admin() {
  echo ""
  read -r -p "Email de l'administrateur (créera un compte Keycloak) : " ADMIN_EMAIL

  echo "Démarrage de Keycloak/cœur pour créer le compte admin..."
  $COMPOSE up -d postgis pgbouncer minio keycloak
  echo "Attente de Keycloak..."
  for _ in $(seq 1 30); do
    $COMPOSE exec -T keycloak curl -sf http://localhost:8080/auth/health/ready >/dev/null 2>&1 && break
    sleep 2
  done

  local kc_token
  kc_token="$($COMPOSE exec -T keycloak curl -sf -X POST \
    http://localhost:8080/auth/realms/master/protocol/openid-connect/token \
    -d client_id=admin-cli -d username=admin -d "password=${KC_PASSWORD}" \
    -d grant_type=password | jq -r .access_token)"
  if [ -z "$kc_token" ] || [ "$kc_token" = "null" ]; then
    echo "✗ Échec d'authentification à l'API Admin Keycloak." >&2
    exit 1
  fi

  local admin_temp_password
  admin_temp_password="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"

  # Idempotent : si l'utilisateur existe déjà (relance de l'installeur),
  # récupérer son id plutôt que d'échouer sur un doublon.
  local existing_id
  existing_id="$($COMPOSE exec -T keycloak curl -sf \
    "http://localhost:8080/auth/admin/realms/geostudio/users?email=${ADMIN_EMAIL}&exact=true" \
    -H "Authorization: Bearer ${kc_token}" | jq -r '.[0].id // empty')"

  if [ -n "$existing_id" ]; then
    echo "✓ Compte admin déjà existant (${ADMIN_EMAIL}) — id réutilisé."
    ADMIN_SUB="$existing_id"
  else
    $COMPOSE exec -T keycloak curl -sf -X POST \
      http://localhost:8080/auth/admin/realms/geostudio/users \
      -H "Authorization: Bearer ${kc_token}" -H "Content-Type: application/json" \
      -d "{\"email\":\"${ADMIN_EMAIL}\",\"username\":\"${ADMIN_EMAIL}\",\"enabled\":true,\"emailVerified\":true,\"credentials\":[{\"type\":\"password\",\"value\":\"${admin_temp_password}\",\"temporary\":true}]}"
    ADMIN_SUB="$($COMPOSE exec -T keycloak curl -sf \
      "http://localhost:8080/auth/admin/realms/geostudio/users?email=${ADMIN_EMAIL}&exact=true" \
      -H "Authorization: Bearer ${kc_token}" | jq -r '.[0].id')"
    echo "✓ Compte admin créé : ${ADMIN_EMAIL} / mot de passe temporaire : ${admin_temp_password}"
    echo "  (à changer à la première connexion — non stocké par ce script au-delà de cet affichage)"
  fi

  set_env_var CORE_ADMIN_SUBS "$ADMIN_SUB"
}

prompt_admin
```

- [ ] **Step 5: Vérifier réellement (nécessite un vrai compte Tailscale)**

Avec un vrai `TS_AUTHKEY` de test disponible, exporté dans l'environnement (évite la question interactive, cf. Step 2) :

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
cd /tmp/geostudio-install-test
export TS_AUTHKEY=tskey-auth-xxxx
INSTALL_YES=1 ./scripts/install.sh <<'EOF'

s3-endpoint-vide-ici-laisser-vide
test@example.com

EOF
```

(La première ligne vide répond à « nom d'hôte public » — vide, donc découverte automatique via le tunnel ; la ligne « laisser vide » simule une réponse vide à la question de cible de sauvegarde en pressant Entrée — remplacer par une vraie valeur vide `EOF`-compatible si le heredoc pose souci en pratique, ajusté empiriquement à l'exécution.) Expected : `.env` contient `GEOSTUDIO_PUBLIC_HOST` renseigné avec un vrai nom `*.ts.net`, `CORE_ADMIN_SUBS` renseigné avec un UUID Keycloak.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 6: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur — découverte d'hôte, tunnel, premier admin Keycloak"
```

---

### Task 4 : lancement final, attente de santé, idempotence (critère §7-6)

**Files:**
- Modify: `scripts/install.sh`

**Interfaces:** consomme l'ensemble des Tasks 1-3 du même fichier ; ne produit rien de consommé ailleurs (dernière étape du script).

- [ ] **Step 1: Lancement complet + attente de santé + seed optionnel**

Ajouter à `scripts/install.sh` :

```bash
launch_stack() {
  echo ""
  echo "Démarrage complet de la stack..."
  local profile_args=()
  for p in "${SELECTED_PROFILES[@]}"; do
    profile_args+=(--profile "$p")
  done
  $COMPOSE "${profile_args[@]}" up -d

  echo "Attente de la disponibilité du cœur..."
  for _ in $(seq 1 30); do
    code="$($COMPOSE exec -T core curl -s -o /dev/null -w '%{http_code}' http://localhost:8200/me 2>/dev/null || echo 000)"
    [ "$code" = "401" ] && break
    sleep 2
  done
  if [ "$code" != "401" ]; then
    echo "✗ Le cœur ne répond pas comme attendu (code ${code}) — vérifiez 'docker compose logs core'." >&2
    exit 1
  fi
  echo "✓ Cœur opérationnel."

  if [ "$SEED_DEMO" = "true" ]; then
    $COMPOSE exec -T core python -m scripts.seed_demo || true
  fi
}

print_summary() {
  echo ""
  echo "═══ GeoStudio est en ligne ═══"
  echo "URL publique : https://${PUBLIC_HOST}/"
  echo "Admin        : ${ADMIN_EMAIL:-<déjà existant>}"
  echo ""
  echo "Prochaines étapes :"
  echo "  - Se connecter avec le compte admin (mot de passe temporaire affiché ci-dessus, à changer)."
  echo "  - Si une cible de sauvegarde a été configurée : générer une paire de clés"
  echo "    age (age-keygen) et renseigner BACKUP_AGE_RECIPIENT dans .env, puis"
  echo "    redémarrer le service backup ('docker compose ... restart backup')."
  echo "  - Conserver .env et la clé privée age en lieu sûr, hors de cette machine."
}

launch_stack
print_summary
```

- [ ] **Step 2: Vérifier l'idempotence (relance sans casse, critère §7-6)**

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
cd /tmp/geostudio-install-test
INSTALL_YES=1 TS_AUTHKEY=<clé-de-test-valide> ./scripts/install.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Expected (premier passage) : tous les services `Up`, message final avec l'URL publique.

```bash
INSTALL_YES=1 TS_AUTHKEY=<même-clé> ./scripts/install.sh
```

Expected (second passage) : `.env` conservé (`✓ .env existe déjà`), compte admin réutilisé (`✓ Compte admin déjà existant`), aucune erreur, stack toujours saine (`docker compose ps` inchangé).

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 3: Rendre le script exécutable et vérifier le non-régression global**

```bash
chmod +x scripts/install.sh
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm test && npm run build
```

Expected : tous verts — ce sous-plan ne touche à aucun code applicatif.

- [ ] **Step 4: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur — lancement, attente de santé, idempotence (critère §7-6)"
```
