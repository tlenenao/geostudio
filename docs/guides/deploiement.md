# Déployer GeoStudio

Quatre cibles, toutes à partir des **images publiées** `ghcr.io/tlenenao/geostudio-*`
(pas de build sur l'hôte). Le tag est toujours explicite : `GEOSTUDIO_VERSION` est
**obligatoire** dans `.env` (le compose de production refuse de démarrer sans, il n'y
a plus de repli sur `latest`).

| Cible | Point d'entrée | Quand |
|---|---|---|
| Docker Compose sur un hôte | `scripts/install.sh` (installeur guidé) | une VM ou un serveur, le cas courant |
| Proxmox | [`deploy/proxmox/README.md`](../../deploy/proxmox/README.md) | VM provisionnée par OpenTofu + Ansible |
| Oracle Cloud (Ampere A1, arm64, tier gratuit) | [`deploy/oci/README.md`](../../deploy/oci/README.md) | cloud, arm64 |
| Kubernetes | [runbook Helm](../runbooks/2026-10-12-deploiement-kubernetes-helm.md) (chart `deploy/helm/geostudio`) | cluster existant |

## Compose (cas général)

```bash
git clone https://github.com/tlenenao/geostudio && cd geostudio
git checkout vX.Y.Z                 # le dépôt et les images doivent porter la même version
./scripts/install.sh                # génère .env et les secrets, pose GEOSTUDIO_VERSION, démarre
```

L'installeur : génère les secrets forts (dont la clé du coffre), configure
Keycloak (realm, URI de redirection à l'hôte public), peut activer les profils
optionnels (`export`, `appexport`, `observability`), le tunnel Tailscale Funnel et
les **sauvegardes chiffrées** planifiées. Variables non interactives :
`INSTALL_YES=1`, `INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `GEOSTUDIO_PUBLIC_HOST`.

Vérifier l'authenticité des images avant de démarrer :
`INSTALL_VERIFY_SIGNATURES=1 ./scripts/install.sh` (exige `cosign`) — voir
[la chaîne d'approvisionnement](../supply-chain.md).

## Après l'installation

- **Santé** : `GET /health` ; `docker compose ps` doit montrer les services `healthy`.
- **Montée de version** : [runbook](../runbooks/2026-10-17-montee-de-version.md)
  (sauvegarde, nouveau tag, vérification, retour arrière).
- **Sauvegarde / restauration** : [runbook](../runbooks/2026-07-24-restauration-sauvegardes.md).
- **Alertes d'exploitation** : [astreinte](../runbooks/2026-10-17-astreinte-alertes.md).
- **Haute disponibilité** : [runbook](../runbooks/2026-10-12-haute-disponibilite-bornee.md).
- **Keycloak existant** : [`deploy/keycloak/README.md`](../../deploy/keycloak/README.md).
- **Mode démo public** (lecture seule) : `CORE_READ_ONLY_MODE=true`.
- **Souveraineté** : `CORE_EXTERNAL_BASEMAPS_ENABLED=false` retire les fonds de carte tiers.
