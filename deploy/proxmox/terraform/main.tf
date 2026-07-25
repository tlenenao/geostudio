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
