# 0011 — Sortie de GeoNode/Superset/Redis (jalon M1)

Statut: acceptée
Source : `CLAUDE.md` « Décisions figées » (pas d'arbitrage `Axx` dédié dans le
document vision — sortie actée comme jalon produit M1, 2026-07-09).

## Contexte

Le fork `gis-project` héritait d'une stack GeoNode (catalogue, permissions)
plus Superset (BI) plus Redis (cache/broker). La stratégie du produit est une
« refonte par étranglement » (option C) : remplacer progressivement GeoNode
par le cœur maison plutôt que de continuer à l'opérer en parallèle.

## Décision

GeoNode, Superset et Redis sont sortis du dépôt (retirés du compose et du
code) au jalon M1 (2026-07-09) — tout code de contenu passe désormais par le
cœur (`ItemClient`).

## Conséquences

- Plus aucune dépendance vers ces trois services dans `docker-compose.yml`
  ni dans le code du shell ou du cœur — toute réapparition serait une
  régression du jalon M1.
- Redis en particulier ne revient pas comme cache/broker « pratique » : la
  file de jobs est procrastinate (ADR-0005, sur Postgres), et tout cache
  applicatif doit être justifié à nouveau plutôt que supposé disponible.
- Le remplacement de la BI (Superset) est traité par le chantier analytics
  propre au produit (datasets/widgets, DuckDB — SP-11/SP-14/SP-16), pas par
  la réintroduction de Superset.
- Ce jalon a rendu le produit « GeoNode-free » : toute nouvelle fonctionnalité
  de catalogue/permissions est développée dans `core/`, jamais en s'appuyant
  sur un reliquat GeoNode.
