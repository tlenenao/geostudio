output "vm_ip" {
  description = "Adresse IP (sans préfixe CIDR) de la VM GeoStudio, à reporter dans inventory.ini (Task 3)"
  value       = split("/", var.ip_address)[0]
}

output "vm_ssh_username" {
  description = "Utilisateur SSH de la VM, à reporter dans inventory.ini (Task 3)"
  value       = var.ssh_username
}
