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
