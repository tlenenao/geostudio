# Lot L13 « Parité long terme » : spec courte (2026-10-19)

Cadrage complet : `docs/revue/audit-2026-10-16/102-l13-cadrage.md`. Décisions D2/D3/D7 conformes aux recommandations §5.

## Périmètre exécuté (classe a)

- **AUD-063** : agrégat DuckDB avec top-N (`orderBy`/`order`/`limit`), opérateurs de filtre (`__ne/__gt/__lt/__contains`) et cache de résultat borné (LRU 128, <= 2000 lignes), clé = liste des fichiers du lac (pas de TTL : toute écriture CDC invalide) + tenant/collection/schéma/`masked_fields`.
- **AUD-062** : requêtes SQL Lab enregistrées par utilisateur (`app/saved_queries/`, migration 0172, 4 routes `/v1/analytics/sql/saved*`, purge/export RGPD couverts, panneau dans SqlLabPage).
- **AUD-131 (D7)** : rafraîchissement planifié par source de données (`DataSource.refreshSeconds` 5-3600 s, `refetchInterval` react-query) ; pas de moteur de streaming.
- **AUD-142** : identify raster `GET /v1/raster/{id}/point` via TiTiler, mêmes gardes que les tuiles (`can()`, limites géographiques, URL S3 jamais fournie par le client).
- **AUD-143** : import FlatGeobuf (`.fgb`), signature « fgb » vérifiée, liste fermée de suffixes.

## Hors périmètre

Classes (b) et (c) : voir le cadrage.
