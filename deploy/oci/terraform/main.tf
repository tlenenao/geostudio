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
      min = 22
      max = 22
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
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_index].name
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

  # `data.oci_core_images.ubuntu_arm` est trié par TIMECREATED DESC :
  # `images[0].id` change dès que Canonical publie une nouvelle image. Or
  # `source_id` force le remplacement de la ressource — un simple `tofu apply`
  # de routine détruirait donc l'instance et son boot volume (toutes les
  # données GeoStudio avec). L'image de base est résolue une seule fois, à la
  # création.
  lifecycle {
    ignore_changes = [source_details[0].source_id]
  }
}
