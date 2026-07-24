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

