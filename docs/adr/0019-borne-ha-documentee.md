# 0019 — Haute disponibilité : borne de la Vague 1 (documentée et testée, pas « réelle »)

Statut: acceptée
Source : ARC-18/ARC-19 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; ARC-32 (HA réelle, hors périmètre) ; SP-49, SP-59, REV-164/354/355/345.

## Contexte

Esri documente une HA bornée à un datacenter (2 portails + LB). GeoStudio est un monolithe `core` avec limiteur de débit en mémoire par process et un `cdc-worker` mono-writer.

## Décision

- Livrer en Vague 1 : un **runbook** (2 instances `core` derrière Traefik, Postgres primaire/standby en streaming, MinIO distribué, RPO/RTO annoncés), un **test de bascule scripté**, et la vérification des invariants à 2 réplicas (jobs procrastinate, CSP, limiteur). Critères : `docker compose up --scale core=2` passe la fumée ; arrêt d'un réplica < 5 s d'indisponibilité mesurée.
- L'écart du limiteur en mémoire (budget par process) est **documenté**, pas corrigé ici. Limiteur partagé (Postgres), élection du `cdc-worker`, `core` sans état total et support contractuel restent dans **ARC-32**.
- Le **drill de restauration** (ARC-19 : sauvegarde → `down -v` → restauration → fumée OIDC) précède ARC-18 et ne tourne que sur une stack jetable, jamais sur la base de référence partagée.

## Conséquences

- Promesse commerciale limitée à « HA documentée et testée » ; toute promesse de HA réelle exige ARC-32.
