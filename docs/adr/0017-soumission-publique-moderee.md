# 0017 — Soumission publique anonyme : écriture `pending` seulement, derrière un jeton

Statut: acceptée
Source : ARC-10 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; ADR 0001 (`can()`), ADR 0016 (clés d'API), A3 (RLS), SP-40 (pièces jointes), SP-58 (RGPD).

## Contexte

L'écriture OGC exige un utilisateur authentifié. Une collectivité doit pouvoir recueillir des signalements citoyens sans compte. C'est un écart contrôlé à « tout passe par `can()` » : il faut le borner explicitement.

## Décision

- Un **`SubmissionToken`** est rattaché à une collection : quota, expiration, révocation, créé par un utilisateur disposant du droit d'écriture sur la collection. Le jeton est un secret machine haché (même patron que l'ADR 0016).
- Route unique `POST /v1/public/submit/{token}`. Elle **ne peut qu'insérer** une ligne au statut `pending` ; jamais lire, modifier ni supprimer.
- Une ligne `pending`/`rejected` est **invisible partout** tant qu'elle n'est pas `approved` : liste de features, tuiles MVT, STAC, DCAT, exports, MCP, DuckDB/lac, WFS. Le filtre est posé au plus bas niveau partagé (RLS/portée de lecture), pas route par route ; la liste des jumelles est vérifiée en revue finale (piège n°14).
- Modération : file `pending → approved|rejected`, réservée aux détenteurs du droit d'écriture ; `audit_log` trace le modérateur ; notification in-app aux modérateurs.
- Anti-abus **sans service tiers** : champ honeypot, rate limit dédié par IP et par jeton (101e requête/h = 429), quota global du jeton. Pièce jointe ≤ 25 Mo, type contrôlé par contenu.
- Les données soumises respectent le schéma de la collection (validation d'écriture normale) ; aucune lecture anonyme n'est élargie (test d'invariant RLS obligatoire).
- RGPD : les soumissions relèvent de `purge_tenant` et de l'anonymisation SP-58 comme toute donnée de collection.

## Conséquences

- Un seul chemin d'écriture anonyme, étroit et auditable. L'identité de l'acteur est un `GuestActor` sans privilège.
- Captcha tiers écarté (dépendance, RGPD) ; à reconsidérer si le spam réel dépasse la modération.
