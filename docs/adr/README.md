# Architecture Decision Records (ADR)

Ce dossier consigne les décisions d'architecture qui contraignent durablement
le code de GeoStudio — le pendant, au niveau du code, des arbitrages `Axx` de
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7-8 et des
« Décisions figées » de `CLAUDE.md`. Une décision qui mérite un ADR est une
décision qu'on ne veut pas re-débattre à chaque session — si elle doit
changer, un nouvel ADR la remplace explicitement (voir « Statut » ci-dessous),
il ne modifie jamais un ADR existant en silence.

## Format (MADR-lite)

Un fichier par décision : `docs/adr/NNNN-titre-court.md`, avec :

- Un en-tête `Statut: acceptée` ou `Statut: remplacée par ADR-xxxx`.
- Une ligne `Source :` pointant vers l'arbitrage `Axx` du document vision
  d'origine (ou vers `CLAUDE.md` « Décisions figées » quand aucun `Axx` dédié
  n'existe) — traçabilité vers le tableau complet options/avantages/
  inconvénients, jamais dupliqué ici.
- `## Contexte` — résumé de 3-6 lignes du problème, pas une reformulation du
  tableau source.
- `## Décision` — l'option retenue, en une phrase.
- `## Conséquences` — ce que ce choix implique concrètement pour le code.

## Quand écrire un ADR

Toute décision qui contraint durablement l'architecture et qu'on ne veut pas
re-débattre — pas chaque choix d'implémentation. Les 35+ arbitrages `Axx` du
document vision ne sont pas tous dupliqués ici : ce dossier n'en retient
qu'un sous-ensemble représentatif des décisions les plus fondamentales et les
plus susceptibles d'être re-débattues sans ce filet. Le document vision reste
la référence complète pour tout arbitrage non repris ici.

## Comment proposer un ADR

Une pull request normale (cf. `CONTRIBUTING.md`) qui ajoute un fichier
`docs/adr/NNNN-titre-court.md` suivant le format ci-dessus, et met à jour le
tableau ci-dessous. Aucun outillage automatisé (pas de générateur de numéro,
pas de lint de format) — un seul committer humain à ce stade ne justifie pas
plus.

## Index

| N° | Titre | Statut | Source |
|---|---|---|---|
| [0001](0001-moteur-autorisation-can.md) | Moteur d'autorisation maison + `can()` unique | acceptée | A1 |
| [0002](0002-groupes-geres-par-le-coeur.md) | Groupes gérés par le cœur, pas par Keycloak | acceptée | A2 |
| [0003](0003-rls-postgis-differee.md) | RLS PostGIS différée à SP-3, données métier seulement | acceptée | A3 |
| [0004](0004-ogc-api-features-ecriture.md) | OGC API Features comme API d'écriture | acceptée | A4 |
| [0005](0005-procrastinate-file-jobs.md) | procrastinate comme file de jobs | acceptée | A5 |
| [0006](0006-cel-langage-expressions.md) | CEL comme langage d'expressions | acceptée | A8 |
| [0007](0007-web-components-lit-sdk.md) | Web Components (Lit) comme technique de SDK | acceptée | A10 |
| [0008](0008-structure-depot-core.md) | Structure du dépôt / module `core/` | acceptée | A14 |
| [0009](0009-tenant-id-audit-log-partout.md) | `tenant_id`+`audit_log` sur toute table dès la première migration | acceptée | CLAUDE.md « Décisions figées » |
| [0010](0010-client-ts-genere-openapi.md) | Client TS généré depuis l'OpenAPI du cœur | acceptée | A11 |
| [0011](0011-sortie-geonode-superset-redis.md) | Sortie de GeoNode/Superset/Redis, jalon M1 | acceptée | CLAUDE.md « Décisions figées » |
