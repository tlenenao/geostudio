# SP-Deploy-e — Provisioning automatisé Proxmox : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatiser le provisioning de la VM Proxmox qui fait tourner GeoStudio en dogfood réel : un module OpenTofu clone un template cloud-init Debian 12 en VM (IP statique, clé SSH), un playbook Ansible installe les prérequis puis invoque `scripts/install.sh` en mode non-interactif — sans toucher au comportement interactif existant du script (usage manuel SP-Deploy-c inchangé).

**Architecture:** Trois couches séquentielles et indépendamment rejouables — OpenTofu (infra, `deploy/proxmox/terraform/`) → Ansible (config + lancement, `deploy/proxmox/ansible/`) → `scripts/install.sh` (existant, étendu pour accepter des réponses pré-remplies via variables d'environnement plutôt que des `read` interactifs). Aucun outil (OpenTofu, Ansible, shellcheck) n'est installé sur la machine locale de développement (pas d'accès `sudo` sans mot de passe dans cet environnement) : toute vérification syntaxique/lint de ce plan passe par des conteneurs Docker officiels jetables, jamais par une installation système.

**Tech Stack:** OpenTofu 1.12 (provider `bpg/proxmox` ~> 0.66), Ansible (modules `ansible.builtin.*`), Bash (extension de `scripts/install.sh`), Docker (exécution des outils de vérification, déjà disponible dans cet environnement).

## Global Constraints

- **Copier verbatim les décisions du design** `docs/superpowers/specs/2026-07-25-sp-deploy-e-provisioning-proxmox-design.md` (§1, décisions E1-E9).
- **Ne jamais changer le comportement interactif par défaut d'`install.sh`** : chaque prompt modifié doit continuer, en l'absence de la variable d'environnement dédiée, à poser exactement la même question qu'aujourd'hui. C'est un critère de non-régression testé par relecture (Task 1).
- **Contrat de variables d'environnement non-interactif** (défini en Task 1, consommé en Task 3) — noms exacts, aucun autre nom n'est introduit ailleurs dans ce plan :
  `INSTALL_YES`, `GEOSTUDIO_PUBLIC_HOST`, `TS_AUTHKEY` (déjà existant), `INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `INSTALL_ADMIN_EMAIL`, `BACKUP_S3_ENDPOINT`, `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`, `BACKUP_S3_BUCKET`.
- **Aucun outil installé sur la machine hôte de dev** (ni `sudo apt-get install ansible/terraform`, ni `pip install`, tous deux vérifiés indisponibles sans mot de passe `sudo` dans cet environnement) : toute commande `tofu`/`ansible-playbook`/`ansible-lint`/`shellcheck` de ce plan s'exécute via `docker run --rm --user "$(id -u):$(id -g)"` sur une image officielle, jamais installée en système.
- **Aucun accès à un vrai Proxmox depuis cet environnement** : les Tasks 2 et 3 sont vérifiées par validation statique (`tofu validate`, `ansible-playbook --syntax-check`, `ansible-lint`), jamais par un `tofu apply`/`ansible-playbook` réel. L'exécution réelle contre le Proxmox du mainteneur est documentée comme procédure manuelle en Task 4 (README), conformément au design (§8 : « exécutée réellement sur le Proxmox du mainteneur, pas assérée ») — même discipline que SP-Deploy-a/b/c pour leurs propres critères d'acceptation.
- **Secrets jamais commités** : jetons API Proxmox, clé privée SSH, `vault.yml` en clair — tous exclus par `.gitignore` (Task 5). Seuls des fichiers `.example` sont commités.
- **Pas d'en-tête SPDX** sur les nouveaux fichiers de ce plan : `deploy/backup/*.sh` (précédent direct dans le même répertoire `deploy/`) n'en porte pas non plus ; la règle SPDX (`scripts/add-license-headers.py`) ne cible que `core/app`, `core/tests`, `shell/src` — hors périmètre ici.
- **Ne pas modifier `CLAUDE.md` (section Feuille de route) ni la feuille de route `docs/vision/2026-07-04-feuille-de-route-geostudio.md`** : le plan SP-Deploy-d (existant, non exécuté) porte déjà la mise à jour documentaire pour toute la famille SP-Deploy une fois a→e terminés — ne pas dupliquer ni entrer en conflit avec cette tâche.
- **Docs en français, code en anglais** (identifiants Terraform/Ansible/Bash), conformément à `CLAUDE.md`.

---

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

  # ETL (SP-15) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-15) — à venir, pas encore disponible dans ce dépôt)"
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

### Task 2 : module OpenTofu — VM Proxmox

**Files:**
- Create: `deploy/proxmox/terraform/versions.tf`
- Create: `deploy/proxmox/terraform/variables.tf`
- Create: `deploy/proxmox/terraform/main.tf`
- Create: `deploy/proxmox/terraform/outputs.tf`
- Create: `deploy/proxmox/terraform/terraform.tfvars.example`
- Create: `deploy/proxmox/terraform/.gitignore`

**Interfaces:**
- Consumes: rien (couche infra pure, aucune dépendance au reste du dépôt).
- Produces: une VM Proxmox joignable en SSH sur `var.ip_address` (sans le préfixe CIDR, exposé en `output.vm_ip`) avec l'utilisateur `var.ssh_username` (défaut `geostudio`) — IP et utilisateur consommés par l'inventaire Ansible de Task 3 (valeurs à reporter à la main dans `inventory.ini`, pas de génération automatique — une seule VM statique, cf. design §3).

- [ ] **Step 1: `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.66"
    }
  }
}
```

- [ ] **Step 2: `variables.tf`**

```hcl
variable "pm_api_url" {
  description = "URL de l'API Proxmox VE (ex. https://192.168.1.10:8006/api2/json)"
  type        = string
}

variable "pm_api_token_id" {
  description = "Identifiant du jeton API Proxmox (ex. root@pam!geostudio)"
  type        = string
}

variable "pm_api_token_secret" {
  description = "Secret du jeton API Proxmox"
  type        = string
  sensitive   = true
}

variable "pm_tls_insecure" {
  description = "Ignorer la vérification TLS de l'API Proxmox (certificat auto-signé par défaut sur Proxmox VE)"
  type        = bool
  default     = true
}

variable "target_node" {
  description = "Nom du nœud Proxmox cible"
  type        = string
}

variable "template_vmid" {
  description = "VMID du template cloud-init Debian 12 (créé manuellement, cf. deploy/proxmox/README.md)"
  type        = number
  default     = 9000
}

variable "vm_id" {
  description = "VMID de la VM GeoStudio à créer"
  type        = number
  default     = 9001
}

variable "vm_name" {
  description = "Nom de la VM"
  type        = string
  default     = "geostudio"
}

variable "cpu_cores" {
  description = "Nombre de vCPU"
  type        = number
  default     = 4
}

variable "memory_mb" {
  description = "RAM allouée, en Mo"
  type        = number
  default     = 8192
}

variable "disk_gb" {
  description = "Taille du disque système, en Go"
  type        = number
  default     = 40
}

variable "disk_datastore_id" {
  description = "Datastore Proxmox où provisionner le disque de la VM"
  type        = string
  default     = "local-lvm"
}

variable "network_bridge" {
  description = "Bridge réseau Proxmox"
  type        = string
  default     = "vmbr0"
}

variable "ip_address" {
  description = "Adresse IPv4 statique de la VM, avec préfixe CIDR (ex. 192.168.1.50/24)"
  type        = string
}

variable "gateway" {
  description = "Passerelle IPv4"
  type        = string
}

variable "ssh_username" {
  description = "Utilisateur créé par cloud-init sur la VM — doit correspondre à ansible_user dans l'inventaire Ansible (Task 3)"
  type        = string
  default     = "geostudio"
}

variable "ssh_public_key" {
  description = "Clé publique SSH injectée dans la VM via cloud-init"
  type        = string
}
```

- [ ] **Step 3: `main.tf`**

```hcl
provider "proxmox" {
  endpoint  = var.pm_api_url
  api_token = "${var.pm_api_token_id}=${var.pm_api_token_secret}"
  insecure  = var.pm_tls_insecure
}

resource "proxmox_virtual_environment_vm" "geostudio" {
  name      = var.vm_name
  node_name = var.target_node
  vm_id     = var.vm_id

  clone {
    vm_id = var.template_vmid
    full  = true
  }

  cpu {
    cores = var.cpu_cores
  }

  memory {
    dedicated = var.memory_mb
  }

  disk {
    datastore_id = var.disk_datastore_id
    interface    = "scsi0"
    size         = var.disk_gb
  }

  network_device {
    bridge = var.network_bridge
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.gateway
      }
    }
    user_account {
      username = var.ssh_username
      keys     = [var.ssh_public_key]
    }
  }

  operating_system {
    type = "l26"
  }

  agent {
    enabled = true
  }
}
```

- [ ] **Step 4: `outputs.tf`**

```hcl
output "vm_ip" {
  description = "Adresse IP (sans préfixe CIDR) de la VM GeoStudio, à reporter dans inventory.ini (Task 3)"
  value       = split("/", var.ip_address)[0]
}

output "vm_ssh_username" {
  description = "Utilisateur SSH de la VM, à reporter dans inventory.ini (Task 3)"
  value       = var.ssh_username
}
```

- [ ] **Step 5: `terraform.tfvars.example`**

```hcl
pm_api_url         = "https://192.168.1.10:8006/api2/json"
pm_api_token_id     = "root@pam!geostudio"
pm_api_token_secret = "CHANGEME"
target_node         = "pve"
ip_address          = "192.168.1.50/24"
gateway             = "192.168.1.1"
ssh_public_key      = "ssh-ed25519 AAAA... geostudio-deploy"
```

- [ ] **Step 6: `.gitignore` du module**

```
.terraform/
terraform.tfstate
terraform.tfstate.*
terraform.tfvars
```

- [ ] **Step 7: Valider (conteneur OpenTofu officiel, aucune installation système)**

Run:
```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/terraform:/workspace" -w /workspace \
  ghcr.io/opentofu/opentofu:1.12 init -backend=false
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/terraform:/workspace" -w /workspace \
  ghcr.io/opentofu/opentofu:1.12 validate
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/terraform:/workspace" -w /workspace \
  ghcr.io/opentofu/opentofu:1.12 fmt -check
```
Expected : `init` télécharge le provider `bpg/proxmox` avec succès ; `validate` répond `Success! The configuration is valid.` ; `fmt -check` ne signale aucun fichier mal formaté (sortie vide, code `0`). Si `fmt -check` échoue, lancer `... fmt` (sans `-check`) pour reformater, puis relire le diff avant de continuer.

- [ ] **Step 8: Nettoyer les artefacts locaux du `init` de vérification**

```bash
rm -rf deploy/proxmox/terraform/.terraform deploy/proxmox/terraform/.terraform.lock.hcl
```
(Le lock file sera régénéré par le mainteneur lors du premier `tofu init` réel — pas commité ici, absence volontaire pour ce module à usage solo.)

- [ ] **Step 9: Commit**

```bash
git add deploy/proxmox/terraform/
git commit -m "feat(deploy): module OpenTofu — provisioning VM Proxmox (SP-Deploy-e)"
```

---

### Task 3 : playbook Ansible — configuration + lancement

**Files:**
- Create: `deploy/proxmox/ansible/inventory.ini.example`
- Create: `deploy/proxmox/ansible/group_vars/all.yml`
- Create: `deploy/proxmox/ansible/group_vars/vault.yml.example`
- Create: `deploy/proxmox/ansible/playbook.yml`

**Interfaces:**
- Consumes: le contrat de variables d'environnement défini en Task 1 (`INSTALL_YES`, `GEOSTUDIO_PUBLIC_HOST`, `TS_AUTHKEY`, `INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `INSTALL_ADMIN_EMAIL`, `BACKUP_S3_*`) ; l'IP/utilisateur produits par Task 2 (`vm_ip`/`vm_ssh_username`, reportés à la main dans `inventory.ini`).
- Produces: rien consommé par un autre fichier de ce plan — nœud terminal de la chaîne.

- [ ] **Step 1: `inventory.ini.example`**

```ini
[geostudio]
geostudio-vm ansible_host=192.168.1.50 ansible_user=geostudio ansible_ssh_private_key_file=~/.ssh/geostudio_proxmox
```

- [ ] **Step 2: `group_vars/all.yml`** (non-secret, committé tel quel)

```yaml
geostudio_repo_url: "https://github.com/tlenenao/geostudio.git"
geostudio_repo_dest: "/home/geostudio/geostudio"
geostudio_public_host: ""
geostudio_profiles: ""
geostudio_seed_demo: false
```

- [ ] **Step 3: `group_vars/vault.yml.example`** (template — le vrai `vault.yml` est chiffré par `ansible-vault` et gitignored, cf. Task 5)

```yaml
vault_ts_authkey: "tskey-auth-CHANGEME"
vault_geostudio_admin_email: "admin@example.com"
vault_backup_s3_endpoint: ""
vault_backup_s3_access_key: ""
vault_backup_s3_secret_key: ""
vault_backup_s3_bucket: "geostudio-backups"
```

- [ ] **Step 4: `playbook.yml`**

```yaml
---
- name: Provisionner GeoStudio sur la VM Proxmox
  hosts: geostudio
  vars_files:
    - group_vars/all.yml
    - group_vars/vault.yml

  tasks:
    - name: Attendre que SSH soit disponible (premier boot cloud-init)
      ansible.builtin.wait_for_connection:
        timeout: 300

    - name: Mettre à jour le cache apt
      become: true
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 3600

    - name: Installer les prérequis système (git, curl)
      become: true
      ansible.builtin.apt:
        name:
          - git
          - curl
        state: present

    - name: Cloner ou mettre à jour le dépôt GeoStudio
      ansible.builtin.git:
        repo: "{{ geostudio_repo_url }}"
        dest: "{{ geostudio_repo_dest }}"
        version: main
        force: false

    - name: Lancer l'installeur GeoStudio (1ère passe — installe Docker si absent, peut s'arrêter là)
      ansible.builtin.command:
        cmd: ./scripts/install.sh
        chdir: "{{ geostudio_repo_dest }}"
      environment: &geostudio_install_env
        INSTALL_YES: "1"
        GEOSTUDIO_PUBLIC_HOST: "{{ geostudio_public_host }}"
        TS_AUTHKEY: "{{ vault_ts_authkey }}"
        INSTALL_PROFILES: "{{ geostudio_profiles }}"
        INSTALL_SEED_DEMO: "{{ '1' if geostudio_seed_demo else '0' }}"
        INSTALL_ADMIN_EMAIL: "{{ vault_geostudio_admin_email }}"
        BACKUP_S3_ENDPOINT: "{{ vault_backup_s3_endpoint }}"
        BACKUP_S3_ACCESS_KEY: "{{ vault_backup_s3_access_key }}"
        BACKUP_S3_SECRET_KEY: "{{ vault_backup_s3_secret_key }}"
        BACKUP_S3_BUCKET: "{{ vault_backup_s3_bucket }}"
      register: install_pass1
      changed_when: true

    # Si ensure_docker (scripts/install.sh) vient d'installer Docker, le
    # script s'arrête volontairement après (exit 0) : l'appartenance au
    # groupe docker du nouvel utilisateur ne prend effet qu'à la prochaine
    # session. reset_connection force Ansible à rouvrir une session SSH
    # neuve avant la 2e passe plutôt que de réutiliser la connexion
    # persistante existante, qui ignorerait ce changement.
    - name: Réinitialiser la connexion SSH (prise en compte du groupe docker)
      ansible.builtin.meta: reset_connection

    - name: Lancer l'installeur GeoStudio (2e passe — idempotente, termine le déploiement)
      ansible.builtin.command:
        cmd: ./scripts/install.sh
        chdir: "{{ geostudio_repo_dest }}"
      environment: *geostudio_install_env
      register: install_pass2
      changed_when: true

    - name: Afficher le résumé de l'installeur
      ansible.builtin.debug:
        var: install_pass2.stdout_lines
```

- [ ] **Step 5: Matérialiser temporairement les fichiers `.example` pour la vérification**

```bash
cp deploy/proxmox/ansible/inventory.ini.example deploy/proxmox/ansible/inventory.ini
cp deploy/proxmox/ansible/group_vars/vault.yml.example deploy/proxmox/ansible/group_vars/vault.yml
```

- [ ] **Step 6: Vérifier la syntaxe et lint (conteneur officiel, aucune installation système)**

Run:
```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-playbook -i inventory.ini --syntax-check playbook.yml
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-lint playbook.yml
```
Expected : `--syntax-check` répond `playbook: playbook.yml` sans erreur (code `0`) ; `ansible-lint` ne remonte aucune erreur bloquante (des avertissements de style sont acceptables, à corriger seulement s'ils sont triviaux).

- [ ] **Step 7: Nettoyer les fichiers matérialisés (ne pas les laisser trackés — ils contiennent des valeurs d'exemple, pas les vraies)**

```bash
rm deploy/proxmox/ansible/inventory.ini deploy/proxmox/ansible/group_vars/vault.yml
```

- [ ] **Step 8: Commit**

```bash
git add deploy/proxmox/ansible/
git commit -m "feat(deploy): playbook Ansible — configuration + lancement non-interactif (SP-Deploy-e)"
```

---

### Task 4 : documentation — prérequis, template cloud-init, guide de bout en bout

**Files:**
- Create: `deploy/proxmox/README.md`

**Interfaces:**
- Consumes: rien (document terminal).
- Produces: rien consommé par du code — référence humaine pour exécuter réellement Task 2/3 sur le vrai Proxmox.

- [ ] **Step 1: Écrire `deploy/proxmox/README.md`**

```markdown
# Provisioning automatisé Proxmox (SP-Deploy-e)

> Spec : `docs/superpowers/specs/2026-07-25-sp-deploy-e-provisioning-proxmox-design.md`.
> Automatise la création de la VM qui fait tourner GeoStudio en dogfood réel
> (SP-Deploy-a/b/c) sur un hyperviseur Proxmox VE déjà installé. Trois étapes
> séquentielles : template cloud-init (une fois, manuel) → OpenTofu (VM) →
> Ansible (configuration + lancement de `scripts/install.sh`).

## 0. Prérequis, une fois par Proxmox

### Jeton API Proxmox

Interface web Proxmox → Datacenter → Permissions → API Tokens → créer un
jeton (ex. `root@pam!geostudio`, décocher « Privilege Separation » pour un
usage solo simple, ou créer un rôle dédié si vous préférez restreindre).
Notez l'ID complet et le secret (affiché une seule fois) — ils vont dans
`terraform.tfvars` (jamais commité, cf. `.gitignore` du module).

### Template cloud-init Debian 12

Sur le Proxmox, en SSH :

```bash
cd /var/lib/vz/template/iso  # ou tout datastore avec le contenu "iso"
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name debian-12-cloudinit-template --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 9000 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm template 9000
```

VMID `9000` est la convention attendue par défaut par `variables.tf`
(`template_vmid`). Adaptez `local-lvm` au nom réel de votre datastore si
différent.

**Vérification du sudo passwordless** (le déploiement en dépend, cf. §2) :
Proxmox accorde par défaut un accès `sudo` sans mot de passe à l'utilisateur
créé via son cloud-init natif (`ciuser`, exposé par le bloc `initialization`
d'OpenTofu). Après la première création de VM (§1), vérifiez :

```bash
ssh -i ~/.ssh/geostudio_proxmox geostudio@<ip> 'sudo -n true && echo OK'
```

Si ce n'est **pas** le cas sur votre version de Proxmox/image cloud, ajoutez
manuellement, une fois, dans la VM :
```bash
echo 'geostudio ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/geostudio
```

### Outils sur votre poste (pas sur le Proxmox, pas dans ce dépôt)

Installez OpenTofu (https://opentofu.org/docs/intro/install/) et Ansible
(`pipx install ansible-core` ou le paquet de votre distribution) sur la
machine depuis laquelle vous lancez le déploiement — généralement votre poste
de travail, pas le Proxmox lui-même.

## 1. Créer la VM (OpenTofu)

```bash
cd deploy/proxmox/terraform
cp terraform.tfvars.example terraform.tfvars
# éditez terraform.tfvars : pm_api_url, pm_api_token_id, pm_api_token_secret,
# target_node, ip_address, gateway, ssh_public_key (contenu de votre clé
# publique SSH, ex. cat ~/.ssh/geostudio_proxmox.pub)
tofu init
tofu apply
```

Notez l'`output vm_ip` — reportez-le dans `inventory.ini` (§2).

## 2. Configurer et lancer GeoStudio (Ansible)

```bash
cd ../ansible
cp inventory.ini.example inventory.ini
# éditez inventory.ini : ansible_host = vm_ip de l'étape 1

cp group_vars/vault.yml.example group_vars/vault.yml
ansible-vault encrypt group_vars/vault.yml
# éditez les valeurs AVANT de chiffrer, ou : ansible-vault edit group_vars/vault.yml
# — vault_ts_authkey (https://login.tailscale.com/admin/settings/keys)
# — vault_geostudio_admin_email
# — vault_backup_s3_* (optionnel — laissez vide pour aucune sauvegarde hors-site)

# éditez éventuellement group_vars/all.yml : geostudio_public_host (vide =
# découverte auto *.ts.net), geostudio_profiles (ex. "observability"),
# geostudio_seed_demo

ansible-playbook -i inventory.ini --ask-vault-pass playbook.yml
```

À la fin, le résumé imprimé par `scripts/install.sh` (URL publique, compte
admin) s'affiche dans la sortie Ansible (tâche « Afficher le résumé »).

## 3. Vérifications réelles (critères §8 de la spec)

Une fois la stack en ligne :
1. `curl -I https://<GEOSTUDIO_PUBLIC_HOST>/` → répond en HTTPS.
2. `ssh geostudio@<vm_ip> 'cd geostudio && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart'` → tous les services remontent (`worker` ne boucle pas — bloqueur corrigé en SP-Deploy-a).
3. Connexion réelle sur l'URL publique avec le compte admin, écriture d'une donnée, relecture.
4. `tofu destroy` puis `tofu apply` + re-run Ansible → cycle rejouable de bout en bout sans intervention manuelle au-delà de ce README.

Ces vérifications se font sur le vrai Proxmox du mainteneur — aucun outil
de ce dépôt ne peut les exécuter à votre place (pas d'accès réseau à votre
Proxmox depuis un environnement de développement générique).
```

- [ ] **Step 2: Vérifier les références de chemins**

```bash
test -f deploy/proxmox/terraform/terraform.tfvars.example && \
test -f deploy/proxmox/ansible/inventory.ini.example && \
test -f deploy/proxmox/ansible/group_vars/vault.yml.example && \
test -f deploy/proxmox/ansible/group_vars/all.yml && \
test -f deploy/proxmox/ansible/playbook.yml && \
echo "OK — tous les fichiers référencés par le README existent"
```
Expected: `OK — tous les fichiers référencés par le README existent`.

- [ ] **Step 3: Commit**

```bash
git add deploy/proxmox/README.md
git commit -m "docs(deploy): guide provisioning Proxmox — prérequis, template cloud-init, bout en bout (SP-Deploy-e)"
```

---

### Task 5 : `.gitignore` racine + vérification d'intégration finale

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: tous les fichiers créés en Task 2/3 (vérifie qu'aucun secret/état généré n'est trackable).
- Produces: rien — dernière tâche du plan.

- [ ] **Step 1: Étendre `.gitignore` racine**

Le `.gitignore` du module Terraform (Task 2, Step 6) couvre déjà
`deploy/proxmox/terraform/`. Ajouter au `.gitignore` racine les deux
fichiers Ansible générés à partir des `.example` (jamais commités, contrairement
à `group_vars/all.yml` qui reste réel et committé) :

Ajouter à la fin de `.gitignore` :
```
deploy/proxmox/ansible/inventory.ini
deploy/proxmox/ansible/group_vars/vault.yml
```

- [ ] **Step 2: Vérifier qu'aucun fichier sensible n'est tracké**

```bash
git status --short deploy/proxmox/
```
Expected: sortie vide (rien à commiter d'inattendu — tous les fichiers de Task 2/3/4 sont déjà commités, aucun `terraform.tfvars`/`inventory.ini`/`vault.yml` réel ne traîne).

- [ ] **Step 3: Vérification d'intégration — relire la cohérence des trois couches**

Confirmer par lecture croisée (aucune commande, les trois fichiers ont été
écrits dans des tasks séparées) :
- `deploy/proxmox/terraform/variables.tf::ssh_username` (défaut `geostudio`)
  correspond à `ansible_user=geostudio` dans
  `deploy/proxmox/ansible/inventory.ini.example`.
- `deploy/proxmox/ansible/group_vars/all.yml::geostudio_repo_dest`
  (`/home/geostudio/geostudio`) est cohérent avec l'utilisateur `geostudio`
  (pas besoin de `become` pour le `git clone`, home directory de cet
  utilisateur).
- Les 10 variables du bloc `environment:` du playbook (Task 3, Step 4)
  correspondent exactement aux 10 noms du contrat Global Constraints — aucun
  nom introduit dans Task 3 qui ne soit pas défini dans Task 1.

- [ ] **Step 4: Non-régression du reste du dépôt (aucun fichier applicatif touché hors Task 1)**

```bash
cd shell && npm run build
cd ../core && uv run pytest && uv run lint-imports
```
Expected: tous verts — seule Task 1 a touché un fichier hors `deploy/proxmox/`, et `scripts/install.sh` n'est exercé par aucune de ces suites (même situation que SP-Deploy-a/b/c, vérifiées par exécution réelle, pas par ces suites).

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore(deploy): gitignore des artefacts Proxmox générés (SP-Deploy-e)"
```
