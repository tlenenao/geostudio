# Provisioning OCI + découplage ETL/QGIS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provisionner GeoStudio sur une instance Oracle Cloud Ampere A1 Flex
(arm64, tier gratuit) via OpenTofu + Ansible, calqué sur `deploy/proxmox/`, et
permettre d'activer le moteur de pipelines no-code (`CORE_ETL_ENABLED`) sans
jamais démarrer le sidecar QGIS (`qgis-worker`, mono-arch amd64), quelle que
soit l'architecture de l'hôte.

**Architecture:** Un module OpenTofu par provider (aucune ressource commune
entre Proxmox et OCI) ; un seul playbook Ansible partagé (`deploy/ansible/`,
déjà agnostique du provider) référencé par les deux ; `scripts/install.sh`
gagne un toggle `CORE_ETL_ENABLED` séparé du profil compose `etl` (qui ne
démarre que `qgis-worker`).

**Tech Stack:** OpenTofu (provider `oracle/oci` ~> 5.0), Ansible, bash
(`scripts/install.sh`), pytest (`core/tests/test_install_script.py`).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-17-provisioning-oci-design.md`.
- Image cible OCI : **Ubuntu 22.04 arm64 uniquement** (pas Oracle Linux) — le
  playbook Ansible partagé utilise `ansible.builtin.apt`, jamais `dnf`.
- Exposition réseau OCI : **SSH (22) uniquement** en ingress dans la security
  list ; tout le trafic applicatif passe par le tunnel Tailscale
  (`docker-compose.prod.yml`, service `tunnel`) — aucun 80/443 ouvert côté OCI.
- `geostudio_profiles` reste **vide en dur** pour la cible OCI (jamais `etl` =
  jamais `qgis-worker`, quelle que soit l'architecture — une décision de
  déploiement, pas une détection).
- `CORE_ETL_ENABLED` (moteur de pipelines : reader.connector, DuckDB) est
  **indépendant** du profil compose `etl` (qui ne démarre que le sidecar
  QGIS) — doit rester activable seul.
- Terraform reste **séparé par provider** (`deploy/proxmox/terraform/` et
  `deploy/oci/terraform/`, aucune abstraction commune) ; seul le playbook
  Ansible est partagé (`deploy/ansible/playbook.yml`).
- Variables sensibles/de sécurité (`admin_ssh_cidr`, `tenancy_ocid`,
  `user_ocid`, `fingerprint`, `private_key_path`, `ssh_public_key`) : **jamais
  de valeur par défaut** — même patron que `deploy/proxmox/terraform/variables.tf`
  (`ip_address`, `gateway`, `ssh_public_key` déjà sans défaut).
- Aucun outil de cet environnement n'a accès à un vrai tenancy OCI ni à
  `tofu`/`ansible` installés localement (vérifié : ni l'un ni l'autre n'est
  sur le PATH) — la vérification de chaque tâche Terraform/Ansible se fait
  par relecture attentive + un contrôle syntaxique exécutable localement
  (`python3 -c "import yaml; yaml.safe_load(...)"` pour le YAML Ansible),
  jamais par un `tofu validate`/`tofu apply` réel. Pas de CI à câbler pour ce
  module (aucun job Proxmox/OCI n'existe dans `.github/workflows/`, même
  état assumé pour OCI).
- Tous les noms d'arguments Terraform utilisés dans ce plan ont été vérifiés
  contre la documentation source réelle du provider `oracle/oci`
  (`github.com/oracle/terraform-provider-oci`, branche `master`,
  `website/docs/{r,d}/*.html.markdown`) en session — pas de mémoire non
  vérifiée (piège CLAUDE.md n°3).

---

### Task 1: `scripts/install.sh` — toggle `CORE_ETL_ENABLED` découplé du sidecar QGIS

**Files:**
- Modify: `scripts/install.sh:102-108` (`profile_label`), `scripts/install.sh:150-154`
  (message `prompt_profiles`), `scripts/install.sh:184-186` (nouvelle fonction
  + appel après `ensure_env_file`)
- Test: `core/tests/test_install_script.py`

**Interfaces:**
- Consumes : `set_env_var` (`scripts/install.sh:177-183`, déjà existante :
  `set_env_var NAME VALUE` écrit `NAME=VALUE` dans `.env`), `confirm`
  (`scripts/install.sh:12-22`, déjà existante).
- Produces : variable d'environnement non-interactive `INSTALL_CORE_ETL_ENABLED`
  (`"1"`/`"0"`), consommée par `deploy/ansible/playbook.yml` en Task 2.

- [ ] **Step 1 : reformuler le libellé du profil `etl` (il ne démarre que le
  sidecar QGIS, pas un moteur ETL général)**

Dans `scripts/install.sh`, remplacer :

```bash
profile_label() {
  case "$1" in
    observability) echo "Observabilité (Grafana/Loki/Tempo/Prometheus)" ;;
    etl) echo "ETL no-code (SP-17)" ;;
    *) echo "$1" ;;
  esac
}
```

par :

```bash
profile_label() {
  case "$1" in
    observability) echo "Observabilité (Grafana/Loki/Tempo/Prometheus)" ;;
    etl) echo "Sidecar QGIS (transform.qgis, isolé, image mono-arch amd64)" ;;
    *) echo "$1" ;;
  esac
}
```

Et, dans `prompt_profiles`, remplacer :

```bash
  # ETL (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-17) — à venir, pas encore disponible dans ce dépôt)"
  fi
```

par :

```bash
  # QGIS (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (Sidecar QGIS (transform.qgis) — à venir, pas encore disponible dans ce dépôt)"
  fi
```

- [ ] **Step 2 : ajouter la fonction `prompt_etl_engine` et son appel**

Dans `scripts/install.sh`, juste après la ligne `ensure_env_file` (ligne 185),
insérer :

```bash
prompt_etl_engine() {
  echo ""
  local etl_enabled=false
  if [ -n "${INSTALL_CORE_ETL_ENABLED+x}" ]; then
    if [ "$INSTALL_CORE_ETL_ENABLED" = "1" ]; then
      etl_enabled=true
    fi
    echo "INSTALL_CORE_ETL_ENABLED=${INSTALL_CORE_ETL_ENABLED} — moteur de pipelines $([ "$etl_enabled" = true ] && echo activé || echo désactivé)."
  elif confirm "Activer le moteur de pipelines no-code (CORE_ETL_ENABLED — reader.connector, DuckDB ; indépendant du sidecar QGIS ci-dessus) ?"; then
    etl_enabled=true
  fi
  set_env_var CORE_ETL_ENABLED "$etl_enabled"
}

prompt_etl_engine
```

Le fichier doit maintenant ressembler à ceci autour de cette zone :

```bash
ensure_env_file

prompt_etl_engine() {
  ...
}

prompt_etl_engine

prompt_public_host() {
```

- [ ] **Step 3 : écrire les tests (rouge d'abord pour le cas d'activation)**

Dans `core/tests/test_install_script.py`, modifier `_run_install` pour fixer
une valeur par défaut non-interactive (même patron que `INSTALL_PROFILES`/
`INSTALL_SEED_DEMO` juste au-dessus) :

```python
def _run_install(install_workdir, fake_bin_path, *, extra_env=None, timeout=30):
    bin_dir, log_file = fake_bin_path
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_BIN_LOG"] = str(log_file)
    env["INSTALL_YES"] = "1"
    env["INSTALL_PROFILES"] = ""
    env["INSTALL_SEED_DEMO"] = "0"
    env["INSTALL_CORE_ETL_ENABLED"] = "0"
    env["GEOSTUDIO_PUBLIC_HOST"] = "geostudio-test.example"
    env["TS_AUTHKEY"] = "tskey-test-fake"
    env["BACKUP_S3_ENDPOINT"] = ""
    env["INSTALL_ADMIN_EMAIL"] = "admin@test.example"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", str(install_workdir / "scripts/install.sh")],
        cwd=install_workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result, log_file.read_text()
```

(seule la ligne `env["INSTALL_CORE_ETL_ENABLED"] = "0"` est ajoutée).

Puis ajouter, à la fin du fichier :

```python
def test_install_enables_the_core_etl_engine_independently_of_the_qgis_profile(
    install_workdir, fake_bin_path
):
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"INSTALL_CORE_ETL_ENABLED": "1"},
    )

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ETL_ENABLED=true" in env_lines


def test_install_leaves_the_core_etl_engine_disabled_by_default(install_workdir, fake_bin_path):
    result, _ = _run_install(install_workdir, fake_bin_path)

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ETL_ENABLED=false" in env_lines
```

- [ ] **Step 4 : lancer les tests avant l'implémentation**

Run (depuis `core/`) :
```bash
cd core && uv run pytest tests/test_install_script.py -v
```
Expected :
- `test_install_enables_the_core_etl_engine_independently_of_the_qgis_profile`
  → **FAIL** (`.env` contient encore `CORE_ETL_ENABLED=false`, jamais écrit à
  `true` puisque `INSTALL_CORE_ETL_ENABLED` n'existe pas encore dans le
  script).
- `test_install_leaves_the_core_etl_engine_disabled_by_default` → **PASS**
  déjà à ce stade (le défaut de `.env.example` est `false`, rien ne le
  modifie encore) — normal, ce test sert de garde de non-régression pour
  l'implémentation qui suit, pas d'un cycle rouge/vert.
- Les 4 tests existants doivent rester **PASS** (aucun changement de
  comportement pour eux).

Si Step 1/Step 2 ont déjà été appliqués avant ce Step 4, inverser l'ordre
d'exécution n'est pas grave (l'important est que les deux nouveaux tests
existent et soient corrects) — mais exécuter Step 4 avant Step 1/2 permet de
confirmer que le premier test échoue bien pour la raison attendue.

- [ ] **Step 5 : exécuter Step 1 et Step 2 (implémentation), puis relancer les tests**

Run :
```bash
cd core && uv run pytest tests/test_install_script.py -v
```
Expected : **6 passed** (les 4 existants + les 2 nouveaux).

- [ ] **Step 6 : commit**

```bash
git add scripts/install.sh core/tests/test_install_script.py
git commit -m "feat(deploy): découple le moteur ETL (CORE_ETL_ENABLED) du sidecar QGIS dans install.sh

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Extraction du playbook Ansible commun + wiring `CORE_ETL_ENABLED`

**Files:**
- Move: `deploy/proxmox/ansible/playbook.yml` → `deploy/ansible/playbook.yml`
- Modify: `deploy/ansible/playbook.yml` (ajout `INSTALL_CORE_ETL_ENABLED`)
- Modify: `deploy/proxmox/ansible/group_vars/all.yml` (ajout
  `geostudio_core_etl_enabled: false`)
- Modify: `deploy/proxmox/README.md` (chemin du playbook dans la commande
  `ansible-playbook`)

**Interfaces:**
- Consumes : `INSTALL_CORE_ETL_ENABLED` (Task 1).
- Produces : `deploy/ansible/playbook.yml` (chemin stable), variable
  `geostudio_core_etl_enabled` (bool, lue depuis `group_vars/all.yml` de
  chaque cible) — consommés par Task 4 (`deploy/oci/ansible/`).

- [ ] **Step 1 : déplacer le playbook**

```bash
mkdir -p deploy/ansible
git mv deploy/proxmox/ansible/playbook.yml deploy/ansible/playbook.yml
```

- [ ] **Step 2 : ajouter `INSTALL_CORE_ETL_ENABLED` au bloc d'environnement partagé**

Dans `deploy/ansible/playbook.yml`, remplacer :

```yaml
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
```

par :

```yaml
      environment: &geostudio_install_env
        INSTALL_YES: "1"
        GEOSTUDIO_PUBLIC_HOST: "{{ geostudio_public_host }}"
        TS_AUTHKEY: "{{ vault_ts_authkey }}"
        INSTALL_PROFILES: "{{ geostudio_profiles }}"
        INSTALL_SEED_DEMO: "{{ '1' if geostudio_seed_demo else '0' }}"
        INSTALL_CORE_ETL_ENABLED: "{{ '1' if geostudio_core_etl_enabled else '0' }}"
        INSTALL_ADMIN_EMAIL: "{{ vault_geostudio_admin_email }}"
        BACKUP_S3_ENDPOINT: "{{ vault_backup_s3_endpoint }}"
        BACKUP_S3_ACCESS_KEY: "{{ vault_backup_s3_access_key }}"
        BACKUP_S3_SECRET_KEY: "{{ vault_backup_s3_secret_key }}"
        BACKUP_S3_BUCKET: "{{ vault_backup_s3_bucket }}"
```

- [ ] **Step 3 : ajouter la variable manquante côté Proxmox (ne pas casser le
  provisioning existant)**

Dans `deploy/proxmox/ansible/group_vars/all.yml`, remplacer :

```yaml
geostudio_repo_url: "https://github.com/tlenenao/geostudio.git"
geostudio_repo_dest: "/home/geostudio/geostudio"
geostudio_public_host: ""
geostudio_profiles: ""
geostudio_seed_demo: false
```

par :

```yaml
geostudio_repo_url: "https://github.com/tlenenao/geostudio.git"
geostudio_repo_dest: "/home/geostudio/geostudio"
geostudio_public_host: ""
geostudio_profiles: ""
geostudio_seed_demo: false
geostudio_core_etl_enabled: false
```

- [ ] **Step 4 : mettre à jour la commande dans le README Proxmox**

Dans `deploy/proxmox/README.md`, remplacer :

```
ansible-playbook -i inventory.ini --ask-vault-pass playbook.yml
```

par :

```
ansible-playbook -i inventory.ini --ask-vault-pass ../../ansible/playbook.yml
```

- [ ] **Step 5 : vérifier la syntaxe YAML (pas d'`ansible-playbook` installé
  dans cet environnement)**

Run :
```bash
python3 -c "
import yaml
yaml.safe_load(open('deploy/ansible/playbook.yml'))
yaml.safe_load(open('deploy/proxmox/ansible/group_vars/all.yml'))
print('YAML OK')
"
```
Expected : `YAML OK` (aucune exception — les expressions Jinja `{{ ... }}`
restent de simples chaînes pour un parseur YAML, donc ce contrôle valide la
structure sans avoir besoin d'Ansible installé).

- [ ] **Step 6 : vérifier qu'aucune référence à l'ancien chemin ne survit**

Run :
```bash
grep -rn "proxmox/ansible/playbook.yml" deploy/ docs/ 2>/dev/null
```
Expected : aucune sortie.

- [ ] **Step 7 : commit**

```bash
git add deploy/ansible/playbook.yml deploy/proxmox/ansible/playbook.yml \
        deploy/proxmox/ansible/group_vars/all.yml deploy/proxmox/README.md
git commit -m "refactor(deploy): extrait le playbook Ansible en commun (deploy/ansible/)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(le `git mv` du Step 1 est capturé automatiquement comme un rename par
`git add` sur les deux chemins.)

---

### Task 3: Module OpenTofu OCI (`deploy/oci/terraform/`)

**Files:**
- Create: `deploy/oci/terraform/versions.tf`
- Create: `deploy/oci/terraform/variables.tf`
- Create: `deploy/oci/terraform/main.tf`
- Create: `deploy/oci/terraform/outputs.tf`
- Create: `deploy/oci/terraform/terraform.tfvars.example`
- Create: `deploy/oci/terraform/.gitignore`

**Interfaces:**
- Consumes : rien (module autonome, aucune dépendance sur les tâches
  précédentes).
- Produces : `output "instance_public_ip"`, `output "instance_ssh_username"`
  — consommés par Task 4 (`deploy/oci/ansible/inventory.ini.example`,
  README).

Tous les noms d'arguments ci-dessous ont été vérifiés contre
`github.com/oracle/terraform-provider-oci` (branche `master`) en session
(cf. Global Constraints).

- [ ] **Step 1 : `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}
```

- [ ] **Step 2 : `variables.tf`**

```hcl
variable "tenancy_ocid" {
  description = "OCID du tenancy OCI"
  type        = string
}

variable "user_ocid" {
  description = "OCID de l'utilisateur (clé API créée pour ce provisioning)"
  type        = string
}

variable "fingerprint" {
  description = "Empreinte de la clé API OCI"
  type        = string
}

variable "private_key_path" {
  description = "Chemin local vers la clé privée API OCI"
  type        = string
}

variable "region" {
  description = "Région OCI cible (ex. eu-marseille-1)"
  type        = string
}

variable "compartment_id" {
  description = "OCID du compartiment cible"
  type        = string
}

variable "admin_ssh_cidr" {
  description = "CIDR autorisé en SSH (22) sur l'instance — jamais 0.0.0.0/0, restreindre à votre IP (ex. 203.0.113.4/32)"
  type        = string
}

variable "ssh_public_key" {
  description = "Clé publique SSH injectée dans l'instance (utilisateur ubuntu)"
  type        = string
}

variable "instance_shape" {
  description = "Shape de calcul (Ampere A1 Flex — tier gratuit)"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "instance_ocpus" {
  description = "Nombre d'OCPU (plafond always free : 4)"
  type        = number
  default     = 4
}

variable "instance_memory_gbs" {
  description = "Mémoire en Go (plafond always free : 24)"
  type        = number
  default     = 24
}

variable "boot_volume_gb" {
  description = "Taille du boot volume, en Go (minimum OCI : 50 ; enveloppe gratuite totale : 200 Go boot+block)"
  type        = number
  default     = 100
}

variable "ubuntu_version" {
  description = "Version d'Ubuntu Canonical arm64 à résoudre (data oci_core_images)"
  type        = string
  default     = "22.04"
}

variable "instance_name" {
  description = "Nom affiché de l'instance"
  type        = string
  default     = "geostudio"
}
```

- [ ] **Step 3 : `main.tf`**

```hcl
provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = var.ubuntu_version
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_vcn" "geostudio" {
  compartment_id = var.compartment_id
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "geostudio-vcn"
  dns_label      = "geostudio"
}

resource "oci_core_internet_gateway" "geostudio" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.geostudio.id
  display_name   = "geostudio-igw"
  enabled        = true
}

resource "oci_core_route_table" "geostudio" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.geostudio.id
  display_name   = "geostudio-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.geostudio.id
  }
}

# Ingress SSH uniquement (var.admin_ssh_cidr, jamais 0.0.0.0/0) — tout le
# trafic applicatif passe par le tunnel Tailscale (docker-compose.prod.yml,
# service `tunnel`), pas par un port ouvert ici (cf. Global Constraints).
resource "oci_core_security_list" "geostudio" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.geostudio.id
  display_name   = "geostudio-sl"

  egress_security_rules {
    protocol         = "all"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = var.admin_ssh_cidr
    source_type = "CIDR_BLOCK"

    tcp_options {
      destination_port_range {
        min = 22
        max = 22
      }
    }
  }
}

resource "oci_core_subnet" "geostudio" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.geostudio.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "geostudio-subnet"
  dns_label         = "geostudiosn"
  route_table_id    = oci_core_route_table.geostudio.id
  security_list_ids = [oci_core_security_list.geostudio.id]
}

resource "oci_core_instance" "geostudio" {
  compartment_id      = var.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  shape               = var.instance_shape
  display_name        = var.instance_name

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.geostudio.id
    assign_public_ip = true
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }
}
```

- [ ] **Step 4 : `outputs.tf`**

```hcl
output "instance_public_ip" {
  description = "Adresse IP publique de l'instance GeoStudio, à reporter dans deploy/oci/ansible/inventory.ini"
  value       = oci_core_instance.geostudio.public_ip
}

output "instance_ssh_username" {
  description = "Utilisateur SSH de l'instance (image Canonical Ubuntu : ubuntu)"
  value       = "ubuntu"
}
```

- [ ] **Step 5 : `terraform.tfvars.example`**

```hcl
tenancy_ocid     = "ocid1.tenancy.oc1..CHANGEME"
user_ocid        = "ocid1.user.oc1..CHANGEME"
fingerprint      = "xx:xx:xx:...:xx"
private_key_path = "~/.oci/oci_api_key.pem"
region           = "eu-marseille-1"
compartment_id   = "ocid1.compartment.oc1..CHANGEME"
admin_ssh_cidr   = "203.0.113.4/32"
ssh_public_key   = "ssh-ed25519 AAAA... geostudio-deploy"
```

- [ ] **Step 6 : `.gitignore` (mêmes exclusions que `deploy/proxmox/terraform/.gitignore`)**

Lire d'abord le fichier existant pour recopier exactement les mêmes règles :
```bash
cat deploy/proxmox/terraform/.gitignore
```
Écrire `deploy/oci/terraform/.gitignore` avec un contenu identique (au
minimum `*.tfstate`, `*.tfstate.*`, `.terraform/`, `terraform.tfvars` —
ajuster seulement si le fichier lu contient d'autres règles).

- [ ] **Step 7 : vérification syntaxique locale (pas de `tofu` installé ici)**

Run :
```bash
python3 -c "
import re
for f in ['versions.tf', 'variables.tf', 'main.tf', 'outputs.tf']:
    text = open(f'deploy/oci/terraform/{f}').read()
    assert text.count('{') == text.count('}'), f'{f}: accolades déséquilibrées'
print('accolades équilibrées sur les 4 fichiers')
"
```
Expected : `accolades équilibrées sur les 4 fichiers`. Ce n'est **pas** un
`tofu validate` réel (aucun binaire ni credentials OCI disponibles ici) —
seulement un filet minimal anti-typo. La vérification de fond reste la
relecture attentive des noms d'arguments (déjà vérifiés contre la doc
source du provider, cf. Global Constraints) et, en dernier ressort, un vrai
`tofu init && tofu validate` sur le poste de l'opérateur qui exécute
réellement le provisioning (cf. `deploy/oci/README.md`, Task 4).

- [ ] **Step 8 : commit**

```bash
git add deploy/oci/terraform/
git commit -m "feat(deploy): ajoute le module OpenTofu de provisioning OCI (Ampere A1 arm64)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Cible Ansible OCI + README

**Files:**
- Create: `deploy/oci/ansible/inventory.ini.example`
- Create: `deploy/oci/ansible/group_vars/all.yml`
- Create: `deploy/oci/ansible/group_vars/vault.yml.example`
- Create: `deploy/oci/README.md`

**Interfaces:**
- Consumes : `deploy/ansible/playbook.yml` (Task 2), `output.instance_public_ip`/
  `output.instance_ssh_username` (Task 3), `INSTALL_CORE_ETL_ENABLED` (Task 1).
- Produces : rien (dernière tâche du plan).

- [ ] **Step 1 : `inventory.ini.example`**

```ini
[geostudio]
geostudio-oci ansible_host=<instance_public_ip Terraform> ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/geostudio_oci
```

- [ ] **Step 2 : `group_vars/all.yml`**

```yaml
geostudio_repo_url: "https://github.com/tlenenao/geostudio.git"
geostudio_repo_dest: "/home/ubuntu/geostudio"
geostudio_public_host: ""
# Jamais "etl" ici : qgis-worker (mono-arch amd64) ne doit jamais tourner sur
# cette cible, quelle que soit l'architecture réelle de l'hôte — une
# décision de déploiement, pas une détection (cf. CLAUDE.md, spec §0/§4).
geostudio_profiles: ""
geostudio_seed_demo: false
# Le moteur de pipelines (reader.connector, DuckDB) est indépendant du
# sidecar QGIS ci-dessus (profil compose etl) — activable seul (Task 1).
geostudio_core_etl_enabled: true
```

- [ ] **Step 3 : `group_vars/vault.yml.example`** (identique au modèle
  Proxmox)

```yaml
vault_ts_authkey: "tskey-auth-CHANGEME"
vault_geostudio_admin_email: "admin@example.com"
vault_backup_s3_endpoint: ""
vault_backup_s3_access_key: ""
vault_backup_s3_secret_key: ""
vault_backup_s3_bucket: "geostudio-backups"
```

- [ ] **Step 4 : `deploy/oci/README.md`**

```markdown
# Provisioning OCI (Oracle Cloud Infrastructure — Ampere A1 Flex, arm64)

> Spec : `docs/superpowers/specs/2026-09-17-provisioning-oci-design.md`.
> Provisionne GeoStudio sur le tier gratuit Oracle Cloud (instance Ampere A1
> Flex, arm64 — la seule offre « always free » avec assez de RAM pour la
> pile par défaut). Deux étapes séquentielles : OpenTofu (réseau + instance)
> → Ansible (configuration + lancement de `scripts/install.sh`, playbook
> partagé avec `deploy/proxmox/`).

## 0. Prérequis, une fois par tenancy OCI

### Clé API OCI

Console OCI → icône profil → « My profile » → « API keys » → « Add API
key » → générer une paire de clés (téléchargez la clé privée). Notez le
`fingerprint` affiché, et l'OCID de l'utilisateur (visible sur la page
« My profile ») et du tenancy (menu profil → « Tenancy: <nom> »). Notez
aussi l'OCID du compartiment cible (Identity → Compartments — le
compartiment racine convient pour un usage solo).

### Outils sur votre poste (pas sur l'instance, pas dans ce dépôt)

Installez OpenTofu (https://opentofu.org/docs/intro/install/) et Ansible
(`pipx install ansible-core` ou le paquet de votre distribution).

## 1. Créer l'instance (OpenTofu)

```bash
cd deploy/oci/terraform
cp terraform.tfvars.example terraform.tfvars
# éditez terraform.tfvars : tenancy_ocid, user_ocid, fingerprint,
# private_key_path, region, compartment_id, admin_ssh_cidr (votre IP
# publique en /32, jamais 0.0.0.0/0), ssh_public_key
tofu init
tofu apply
```

Notez l'`output instance_public_ip` — reportez-le dans `inventory.ini` (§2).

**Note capacité** : Ampere A1 Flex sur le tier gratuit connaît des pénuries
de capacité fréquentes selon la région (`tofu apply` échoue avec
`Out of host capacity`) — pas de retry automatisé ici, relancez `tofu apply`
manuellement (éventuellement dans une autre région/AD) jusqu'à ce que la
capacité soit disponible.

## 2. Configurer et lancer GeoStudio (Ansible)

```bash
cd ../ansible
cp inventory.ini.example inventory.ini
# éditez inventory.ini : ansible_host = instance_public_ip de l'étape 1

cp group_vars/vault.yml.example group_vars/vault.yml
ansible-vault encrypt group_vars/vault.yml
# éditez les valeurs AVANT de chiffrer, ou : ansible-vault edit group_vars/vault.yml
# — vault_ts_authkey (https://login.tailscale.com/admin/settings/keys)
# — vault_geostudio_admin_email
# — vault_backup_s3_* (optionnel — laissez vide pour aucune sauvegarde hors-site)

# éditez éventuellement group_vars/all.yml : geostudio_public_host (vide =
# découverte auto *.ts.net), geostudio_seed_demo — NE PAS toucher
# geostudio_profiles (doit rester vide : qgis-worker est mono-arch amd64,
# incompatible avec cette instance arm64)

ansible-playbook -i inventory.ini --ask-vault-pass ../ansible/playbook.yml
```

À la fin, le résumé imprimé par `scripts/install.sh` (URL publique, compte
admin) s'affiche dans la sortie Ansible (tâche « Afficher le résumé »).

## 3. Vérifications réelles (critères §6 de la spec)

Une fois la stack en ligne :
1. `curl -I https://<nom *.ts.net>/` → répond en HTTPS.
2. `ssh -i ~/.ssh/geostudio_oci ubuntu@<instance_public_ip> 'cd geostudio && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart'` → tous les services remontent.
3. Connexion réelle sur l'URL publique avec le compte admin, écriture d'une donnée, relecture.
4. Vérifier que `qgis-worker` n'apparaît **jamais** dans `docker compose ps` sur cette instance (`geostudio_profiles` vide).
5. `tofu destroy` puis `tofu apply` + re-run Ansible → cycle rejouable de bout en bout sans intervention manuelle au-delà de ce README.

Ces vérifications se font sur le vrai tenancy OCI du mainteneur — aucun
outil de ce dépôt ne peut les exécuter à votre place (pas d'accès réseau à
votre tenancy depuis un environnement de développement générique).
```

- [ ] **Step 5 : vérification syntaxique locale**

Run :
```bash
python3 -c "
import yaml
yaml.safe_load(open('deploy/oci/ansible/group_vars/all.yml'))
yaml.safe_load(open('deploy/oci/ansible/group_vars/vault.yml.example'))
print('YAML OK')
"
```
Expected : `YAML OK`.

- [ ] **Step 6 : commit**

```bash
git add deploy/oci/ansible/ deploy/oci/README.md
git commit -m "docs(deploy): ajoute la cible Ansible OCI + le guide de provisioning

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Couverture de la spec** :
- §2 (extraction playbook commun) → Task 2.
- §3 (module Terraform OCI : provider, réseau, security list SSH-only,
  instance, boot volume, sorties) → Task 3.
- §4 (Ansible OCI : inventory, group_vars, profils vides,
  `geostudio_core_etl_enabled`) → Task 4.
- §5 (toggle `CORE_ETL_ENABLED`, reformulation `profile_label`) → Task 1.
- §6 (README OCI, vérifications réelles, note capacité) → Task 4.
- §7 (hors périmètre) : aucune tâche ne l'adresse, comme prévu.

**Placeholders** : aucun — chaque step contient soit le contenu de fichier
complet, soit une commande exacte avec sortie attendue.

**Cohérence des noms** : `INSTALL_CORE_ETL_ENABLED` (Task 1) →
`geostudio_core_etl_enabled` (Task 2/4, group_vars) →
`{{ '1' if geostudio_core_etl_enabled else '0' }}` (Task 2, playbook) — même
variable suivie de bout en bout. `output.instance_public_ip`/
`instance_ssh_username` (Task 3) → `inventory.ini.example`/README (Task 4) —
cohérent.
