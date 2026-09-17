output "instance_public_ip" {
  description = "Adresse IP publique de l'instance GeoStudio, à reporter dans deploy/oci/ansible/inventory.ini"
  value       = oci_core_instance.geostudio.public_ip
}

output "instance_ssh_username" {
  description = "Utilisateur SSH de l'instance (image Canonical Ubuntu : ubuntu)"
  value       = "ubuntu"
}
