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

L'image de base est résolue une seule fois à la création — les futures
publications d'image Canonical ne déclenchent pas un remplacement destructif
de l'instance existante.

**Note capacité** : Ampere A1 Flex sur le tier gratuit connaît des pénuries
de capacité fréquentes selon la région (`tofu apply` échoue avec
`Out of host capacity`) — pas de retry automatisé ici, relancez `tofu apply`
manuellement jusqu'à ce que la capacité soit disponible. Pour viser un autre
domaine de disponibilité de la même région sans toucher à `main.tf`, changez
`availability_domain_index` (0, 1, 2…) dans `terraform.tfvars` ; pour changer
de région, c'est la variable `region`.

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

ansible-playbook -i inventory.ini --ask-vault-pass ../../ansible/playbook.yml
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
