# SP-L4 — Multi-tenant et gouvernance (spec)

Lot L4 de l'audit 2026-10-16 (`docs/revue/audit-2026-10-16/99-synthese.md`) : AUD-010, 011, 092,
093, 095, 097, 098, 120, 121. Décision D4 : **instance dédiée par client d'abord**, pas de SaaS
multi-tenant avant ce lot ; AUD-011 corrigé sans attendre.

Chaque AUD a été relu dans le code avant d'être traité (piège n°12). Migrations : 0120 à 0123.

## Décisions

| AUD | Décision | Livré |
|---|---|---|
| 011 | Fermé. Supprimer une collection supprime sa table `ingest_*`/`query_*` ; une table gérée n'est plus proposée comme « candidate ». | `ddl.drop_managed_table` |
| 093 | Fermé. Un champ pièce jointe `sensible` est masqué comme une colonne sensible (liste, fichier, suppression, MCP). | `masked_attachment_keys` |
| 095 | Partiel. WFS était déjà borné ; ajout d'un groupe de débit `discovery` (STAC/DCAT/Records anonymes) et d'un `statement_timeout` sous SAVEPOINT sur l'emprise STAC. | `ratelimit`, `stac/extent.py` |
| 092 | Fermé. `audit_log` append-only par trigger (garde levée par le GUC `app.audit_maintenance`) ; chaîne de hachage scellée **de façon asynchrone** (pas de verrou sur le chemin d'écriture, donc pas de deadlock) ; le `payload` est hors hachage, donc effaçable (RGPD) sans casser la chaîne ; rétention `CORE_AUDIT_RETENTION_DAYS` avec archive S3. | 0120, `app/audit/{chain,retention,store}.py` |
| 120 | Fermé. Export RGPD des données d'un utilisateur. | `compliance/export.py` |
| 121 | Fermé. Un nettoyage S3 raté ne produit plus un reçu `done` : statut `done_with_s3_pending` + rattrapage périodique ; journal d'effacement S3 (un objet par événement, hors sauvegardes) rejouable par CLI après restauration. Reçu lisible entre tenants (M1) fermé : `purged_tenant_id`. | 0121, `compliance/{journal,replay,purge}.py` |
| 098 | Fermé pour le périmètre ci-dessous. Table `tenant_limits` (NULL = limite d'instance) pour items/collections/stockage/utilisateurs/runs actifs ; plafond d'utilisateurs à la création JIT ; plafond de runs actifs au point unique `create_run_unless_active`. | 0122 |
| 097 | Partiel. `expires_at` sur les partages item/collection, lu par un filtre unique `share_active()` sur les 6 lecteurs. | 0123 |
| 010 | **Différé** (D4). Le tenant reste résolu comme « default » ; la résolution par jeton/hôte et l'API des tenants sont le SP multi-tenant ultérieur. Rien ne l'empêche : toutes les surfaces portent déjà `tenant_id`. | — |

## Limites assumées

- `tenant_limits` n'a pas d'API d'écriture : renseignée par l'opérateur (SQL). Une route admin
  est un suivi.
- Plafond de runs actifs : le verrou advisory est par pipeline, deux pipelines différents du même
  tenant peuvent dépasser le plafond d'un run en concurrence stricte.
- AUD-097 : pas de RLS par attribut ni de vues filtrées ; pas de cible tenant/utilisateur/rôle.
- Un partage expiré reste listé par `GET .../sharing` (l'auteur le voit) mais n'ouvre plus aucun droit.
- `S3_COMPLIANCE_BUCKET` est exclu de la sauvegarde exprès : restaurer une base ancienne ne doit
  pas rétrograder le journal qui sert à rejouer les effacements postérieurs.
