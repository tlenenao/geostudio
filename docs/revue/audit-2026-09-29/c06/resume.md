# c06 — CI, déploiement, ops (audit de code)

## Périmètre couvert
- .github/workflows/* (ci, release, publish-edge, _build-and-push, gitleaks, desktop-etl-webdriver), dependabot.yml, protection de branche (API GitHub).
- docker-compose.yml + docker-compose.prod.yml par valeur (fusion YAML : restart, healthcheck, ports, images, pièges !reset/!override).
- deploy/backup (backup.sh, restore.sh, entrypoint.sh, retention.py), scripts/install.sh, bootstrap-env.sh, deploy/ansible/playbook.yml, .env.example, Dockerfiles (bases, USER), fichiers de secrets suivis (aucun secret suivi : vault.yml, tfvars, tfstate sont ignorés).

## Non couvert
- Pas de docker : aucun compose config réel, aucun build, aucun restore/backup exécuté ; Terraform (Proxmox/OCI) lu en surface seulement ; deploy/keycloak, observability (dashboards/alertes) non audités ; codeql.yml et desktop-etl-spike/sidecar-freeze non relus en détail ; disponibilité réelle des images GHCR non vérifiée (scope read:packages absent).
- Faits déjà connus non re-signalés : audit pré-release #3 (e2e-windows), #9 (stac item-search non bloquant), worktrees orphelins.

## Méthode
Lecture directe des fichiers, fusion des deux compose via PyYAML, exécutions ciblées (sed d'upsert, gh run list/view, gh api, test_retention via uv --with pytest, --check-fresh local).

## Commandes lancées
gh run list/view ci.yml ; gh api .../branches/main/protection ; python3 (fusion compose) ; bash reproduction sed ; uv run --with pytest pytest deploy/backup/test_retention.py ; feature_health_cli.py --check-fresh ; audit_findings.py validate.
