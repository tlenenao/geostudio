# 0009 — `tenant_id` et `audit_log` sur toute table/écriture dès la première migration

Statut: acceptée
Source : `CLAUDE.md` « Décisions figées » (pas d'arbitrage `Axx` dédié dans le
document vision — cette décision est directement actée comme non-négociable
dans le guide de travail du dépôt).

## Contexte

GeoStudio est conçu dès le départ comme un produit multi-tenant, et comme un
produit dont chaque écriture doit pouvoir être auditée (conformité, RGPD,
débogage d'incident). Introduire ces deux colonnes après coup sur un schéma
déjà peuplé est un chantier de migration lourd et risqué (rétro-affectation
de `tenant_id` sur des lignes existantes, notamment).

## Décision

`tenant_id` et un mécanisme d'`audit_log` sont posés sur toute table/écriture
dès la toute première migration Alembic du cœur — pas différés à un futur
chantier « multi-tenant » ou « conformité ».

## Conséquences

- Toute nouvelle table du cœur porte `tenant_id` par construction ; toute
  nouvelle route d'écriture passe par le point d'écriture de l'audit
  (`app.audit.writer`, seul point d'écriture — cf. SP-39, invariant à
  préserver pour toute future table de job).
- Le comparateur modèle↔Alembic de SP-43
  (`core/tests/test_model_alembic_parity.py`) vérifie mécaniquement que
  cette discipline ne dérive pas silencieusement.
- Le RGPD (SP-58, `purge_tenant`) s'appuie directement sur cette colonne pour
  énumérer les tables tenant-scoped à purger — une table qui l'omettrait
  serait invisible à la purge.
