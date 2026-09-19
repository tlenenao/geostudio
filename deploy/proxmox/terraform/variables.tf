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

variable "cpu_type" {
  description = "Modèle de CPU QEMU. Le défaut Proxmox (kvm64) n'expose pas x86-64-v2 (SSE4.2/POPCNT), ce que les images récentes (Keycloak, MinIO) exigent au démarrage (`Fatal glibc error: CPU does not support x86-64-v2`) ; \"host\" expose le CPU physique du nœud — acceptable ici car ce module cible un nœud Proxmox unique sans cluster/migration à vif."
  type        = string
  default     = "host"
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
