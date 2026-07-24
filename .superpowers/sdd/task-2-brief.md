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

