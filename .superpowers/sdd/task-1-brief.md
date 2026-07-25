### Task 1 : `scripts/install.sh` — mode non-interactif par variables d'environnement

**Files:**
- Modify: `scripts/install.sh:113-146` (fonction `prompt_profiles`)
- Modify: `scripts/install.sh:168-208` (fonction `prompt_public_host`)
- Modify: `scripts/install.sh:218-235` (fonction `prompt_backup_target`)
- Modify: `scripts/install.sh:240-242` (début de la fonction `prompt_admin`)

**Interfaces:**
- Consumes: rien de nouveau — mêmes fonctions/variables globales existantes (`SELECTED_PROFILES`, `SEED_DEMO`, `PUBLIC_HOST`, `ADMIN_EMAIL`, `set_env_var`, `confirm`).
- Produces: le contrat de variables d'environnement listé dans Global Constraints, consommé par le playbook Ansible de Task 3.

**Règle appliquée aux quatre fonctions** : si la variable d'environnement dédiée est **définie** (même vide, testée avec `${VAR+x}` — teste la présence, pas le contenu, pour distinguer « non fournie » de « fournie vide = choix explicite »), sauter le `read` correspondant et utiliser sa valeur ; sinon, comportement interactif inchangé.

- [ ] **Step 1: Modifier `prompt_profiles` — profils et seed démo non-interactifs**

Remplacer (lignes 113-146) :

```bash
prompt_profiles() {
  local available
  local label
  local compose_err
  compose_err="$(mktemp)"
  if ! available="$($COMPOSE config --profiles 2>"$compose_err")"; then
    echo "✗ Impossible de lire la configuration Docker Compose :" >&2
    cat "$compose_err" >&2
    rm -f "$compose_err"
    exit 1
  fi
  rm -f "$compose_err"

  echo ""
  echo "── Profils disponibles ──"
  while IFS= read -r profile; do
    [ -z "$profile" ] && continue
    label="$(profile_label "$profile")"
    if confirm "Activer : ${label} ?"; then
      SELECTED_PROFILES+=("$profile")
    fi
  done <<< "$available"

  # ETL (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-17) — à venir, pas encore disponible dans ce dépôt)"
  fi

  echo ""
  if confirm "Charger des données de démo (collections incidents/points_interet, publiques, éditables) ?"; then
    SEED_DEMO=true
  fi
}
```

par :

```bash
prompt_profiles() {
  local available
  local label
  local compose_err
  compose_err="$(mktemp)"
  if ! available="$($COMPOSE config --profiles 2>"$compose_err")"; then
    echo "✗ Impossible de lire la configuration Docker Compose :" >&2
    cat "$compose_err" >&2
    rm -f "$compose_err"
    exit 1
  fi
  rm -f "$compose_err"

  echo ""
  echo "── Profils disponibles ──"
  if [ -n "${INSTALL_PROFILES+x}" ]; then
    echo "INSTALL_PROFILES=\"${INSTALL_PROFILES}\" — sélection non-interactive."
    while IFS= read -r profile; do
      [ -z "$profile" ] && continue
      label="$(profile_label "$profile")"
      if [[ ",${INSTALL_PROFILES}," == *",${profile},"* ]]; then
        echo "  ✓ ${label}"
        SELECTED_PROFILES+=("$profile")
      else
        echo "  ✗ ${label}"
      fi
    done <<< "$available"
  else
    while IFS= read -r profile; do
      [ -z "$profile" ] && continue
      label="$(profile_label "$profile")"
      if confirm "Activer : ${label} ?"; then
        SELECTED_PROFILES+=("$profile")
      fi
    done <<< "$available"
  fi

  # ETL (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-17) — à venir, pas encore disponible dans ce dépôt)"
  fi

  echo ""
  if [ -n "${INSTALL_SEED_DEMO+x}" ]; then
    if [ "$INSTALL_SEED_DEMO" = "1" ]; then
      SEED_DEMO=true
    fi
    echo "INSTALL_SEED_DEMO=${INSTALL_SEED_DEMO} — démo $([ "$SEED_DEMO" = true ] && echo activée || echo désactivée)."
  elif confirm "Charger des données de démo (collections incidents/points_interet, publiques, éditables) ?"; then
    SEED_DEMO=true
  fi
}
```

- [ ] **Step 2: Modifier `prompt_public_host` — hôte public non-interactif**

Remplacer les 3 premières lignes du corps (lignes 168-171) :

```bash
prompt_public_host() {
  echo ""
  read -r -p "Nom d'hôte public (laisser vide pour le découvrir via Tailscale Funnel) : " PUBLIC_HOST_INPUT
  # TS_AUTHKEY déjà exporté dans l'environnement (automatisation, Step 5 de
  # cette tâche) : ne pas redemander — sinon, question interactive.
```

par :

```bash
prompt_public_host() {
  echo ""
  if [ -n "${GEOSTUDIO_PUBLIC_HOST+x}" ]; then
    PUBLIC_HOST_INPUT="$GEOSTUDIO_PUBLIC_HOST"
    if [ -n "$PUBLIC_HOST_INPUT" ]; then
      echo "Nom d'hôte public : ${PUBLIC_HOST_INPUT} (GEOSTUDIO_PUBLIC_HOST)"
    else
      echo "GEOSTUDIO_PUBLIC_HOST défini vide — découverte automatique via Tailscale Funnel."
    fi
  else
    read -r -p "Nom d'hôte public (laisser vide pour le découvrir via Tailscale Funnel) : " PUBLIC_HOST_INPUT
  fi
  # TS_AUTHKEY déjà exporté dans l'environnement (automatisation, Step 5 de
  # cette tâche) : ne pas redemander — sinon, question interactive.
```

Le reste de la fonction (lignes 172-208 : lecture de `TS_AUTHKEY` si absent, démarrage du tunnel, retour anticipé si `PUBLIC_HOST_INPUT` non vide, boucle de découverte auto) **ne change pas** — il consomme déjà `PUBLIC_HOST_INPUT`, peu importe sa provenance.

- [ ] **Step 3: Modifier `prompt_backup_target` — cible de sauvegarde non-interactive**

Remplacer (lignes 218-235) :

```bash
prompt_backup_target() {
  echo ""
  read -r -p "Cible de sauvegarde hors-site (endpoint S3-compatible, optionnel — Entrée pour ignorer) : " s3_endpoint
  if [ -n "$s3_endpoint" ]; then
    read -r -p "  Access key : " s3_access
    read -r -s -p "  Secret key : " s3_secret
    echo
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
```

par :

```bash
prompt_backup_target() {
  echo ""
  local s3_endpoint s3_access s3_secret s3_bucket
  if [ -n "${BACKUP_S3_ENDPOINT+x}" ]; then
    echo "BACKUP_S3_ENDPOINT défini — cible de sauvegarde non-interactive."
    s3_endpoint="$BACKUP_S3_ENDPOINT"
    s3_access="${BACKUP_S3_ACCESS_KEY:-}"
    s3_secret="${BACKUP_S3_SECRET_KEY:-}"
    s3_bucket="${BACKUP_S3_BUCKET:-geostudio-backups}"
  else
    read -r -p "Cible de sauvegarde hors-site (endpoint S3-compatible, optionnel — Entrée pour ignorer) : " s3_endpoint
    if [ -n "$s3_endpoint" ]; then
      read -r -p "  Access key : " s3_access
      read -r -s -p "  Secret key : " s3_secret
      echo
      read -r -p "  Bucket [geostudio-backups] : " s3_bucket
      s3_bucket="${s3_bucket:-geostudio-backups}"
    fi
  fi

  if [ -n "$s3_endpoint" ]; then
    set_env_var BACKUP_S3_ENDPOINT "$s3_endpoint"
    set_env_var BACKUP_S3_ACCESS_KEY "$s3_access"
    set_env_var BACKUP_S3_SECRET_KEY "$s3_secret"
    set_env_var BACKUP_S3_BUCKET "$s3_bucket"
    echo "  Rappel : générez une paire de clés age (age-keygen) et renseignez la clé"
    echo "  PUBLIQUE dans BACKUP_AGE_RECIPIENT — gardez la clé privée hors de cette machine."
  else
    echo "  Aucune cible hors-site — les sauvegardes resteront locales (avertissement du service backup à chaque exécution)."
  fi
}
```

- [ ] **Step 4: Modifier `prompt_admin` — email admin non-interactif**

Remplacer les 2 premières lignes du corps (lignes 240-242) :

```bash
prompt_admin() {
  echo ""
  read -r -p "Email de l'administrateur (créera un compte Keycloak) : " ADMIN_EMAIL
```

par :

```bash
prompt_admin() {
  echo ""
  if [ -n "${INSTALL_ADMIN_EMAIL:-}" ]; then
    ADMIN_EMAIL="$INSTALL_ADMIN_EMAIL"
    echo "Email administrateur : ${ADMIN_EMAIL} (INSTALL_ADMIN_EMAIL)"
  else
    read -r -p "Email de l'administrateur (créera un compte Keycloak) : " ADMIN_EMAIL
  fi
```

Note : ce test utilise `-n` (valeur non vide requise), pas `+x` — contrairement aux trois autres prompts, un email admin ne peut pas être « explicitement vide » : c'est le seul champ obligatoire du flux. `ADMIN_EMAIL` reste une variable globale (pas de `local`), exactement comme dans le script actuel — `print_summary` la lit après coup.

- [ ] **Step 5: Vérifier la syntaxe (bash)**

Run: `bash -n scripts/install.sh`
Expected: aucune sortie, code de sortie `0`.

- [ ] **Step 6: Lint shellcheck (conteneur jetable, aucune installation système)**

Run:
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/mnt -w /mnt \
  koalaman/shellcheck:stable scripts/install.sh
```
Expected: pas de nouvelle alerte introduite par rapport à l'état avant modification (si des avertissements préexistants apparaissent déjà sur des lignes non touchées par ce Step, les laisser — hors périmètre).

- [ ] **Step 7: Relecture de non-régression du chemin interactif**

Relire les 4 fonctions modifiées et confirmer, pour chacune, que la branche `else` reproduit **exactement** le comportement d'avant (mêmes messages, mêmes `read`, aucune ligne supprimée) — condition explicite de Global Constraints. Aucune commande, vérification par lecture.

- [ ] **Step 8: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): install.sh — mode non-interactif par variables d'environnement (SP-Deploy-e)"
```

---

