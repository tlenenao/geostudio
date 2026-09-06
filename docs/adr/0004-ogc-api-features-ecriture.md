# 0004 — OGC API Features comme API d'écriture des données

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A4 —
Forme de l'API d'écriture des features (SP-3)

## Contexte

Le cœur doit exposer une API d'écriture pour les features des collections
métier. Options considérées : un standard OGC (OGC API Features Part 1+4),
un REST maison non conforme, ou l'intégration d'un serveur OGC clef en main
(pygeoapi).

## Décision

OGC API Features Part 1+4, implémentées directement dans le cœur (sous-
ensemble utile d'abord : GeoJSON, CRS84 + CRS courants, conformité
progressive) — pas de REST maison, pas de service pygeoapi séparé.

## Conséquences

- Le cœur remplace `pg_featureserv` : un service de moins à opérer.
- Interopérabilité native avec QGIS et l'écosystème OGC, sans couche de
  traduction.
- Effort de conformité (CRS, ETags, structure des collections) plus élevé
  qu'un REST maison, assumé pour éviter une dette d'interop à rattraper plus
  tard.
- Le contrôle transactionnel fin avec `can()`/`audit_log` reste dans le cœur
  (pas délégué à un service tiers comme pygeoapi l'aurait exigé via des
  plugins).
