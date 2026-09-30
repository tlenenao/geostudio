# Audit c01 — Authz, RLS, IDOR (code) — résumé

14 findings dans `findings.jsonl` : 4 S2, 8 S3, 2 S4. Huit sont `verified` par un PoC exécuté, six sont `probable` (lecture de code).

## Périmètre couvert

- **Routes `core/app/**/routes.py`** : chaque route a été associée à ses dépendances d'authentification (`get_current_user`, `require_privilege`, `require_any_privilege`, `can()`). Pour cela, on parcourt `app.routes` et le `original_router.routes` des `_IncludedRouter` ; la carte produite est gardée dans le scratchpad, hors dépôt. Le chemin réel a été suivi sur items, sharing, share-links, configs, collections, features/tiles, ingestion, export, tileset3d/terrain3d, users/roles, secrets, pipelines, reports et alerts.
- **Masquage de colonnes GAP-22** : édition de `sensitiveFields` (c01-001), cache des tuiles MVT (c01-007), écrasement par PUT depuis le formulaire (c01-004).
- **Rôles et privilèges** : auto-promotion par `admin.users.manage` (c01-002), privilèges catalogués mais jamais appliqués côté serveur (c01-010).
- **Liens de partage et embed** : lien racine jamais recoupé avec les droits de son créateur (c01-005), IDOR sur la révocation (c01-006), lecture du partage par tout lecteur (c01-013).
- **MCP** : outils d'alerte hors inventaire `@write_tool` et sans garde lecture seule (c01-008), outils de lecture non audités (c01-009). `resolve_actor` a été relu : il reprend bien les permissions de l'utilisateur.
- **Exécution différée avec les droits du propriétaire** : rapports et alertes (c01-014), secrets de connecteur sans ACL (c01-003).
- **Vérifié sans défaut nouveau** : portée des listes d'items, `add_member` réservé au créateur du groupe, validation des nœuds de pipeline (lecture/écriture de collection vérifiée contre l'auteur de l'enregistrement), routes harvest ArcGIS, notifications, STAC et DCAT (masquage présent), routes publiques (tenant DEFAULT + publié), gel appexport (collections `is_public` uniquement).
- **Déjà connus, non re-signalés** : GAP-82/REV-185, REV-174, REV-186/187/188, REV-197, et le contournement du masquage par `reader.collection` dans les pipelines (entrée GAP-22). Ils sont cités en `related_gap` quand c'est pertinent.

## Périmètre NON couvert (et pourquoi)

- **RLS PostgreSQL réelle** (`gis_rls` / `gis_rls_masked`, politiques par collection) : aucun `postgis-test` n'est disponible et la consigne interdit de toucher la stack. Les PoC tournent sur SQLite avec `rls_scope` neutralisé. Ce qui a été testé, c'est la logique applicative de garde, pas les politiques SQL.
- **OGC API Features en écriture sur une vraie base** : le défaut c01-004 est déduit du SQL généré et du code du formulaire. Il n'a pas été exécuté contre PostGIS.
- **`admin_tools`, copilote, compliance/quotas, gestion des rôles sur mesure** : ces modules n'ont été que survolés, faute de temps. Ils ne font l'objet d'aucun finding.
- **Routes `/embed/:token` côté shell** : hors du périmètre code du cœur. Pas de Playwright pour ce groupe.

## Méthode

1. Lecture des listes de défauts déjà connus (audit pré-release, backlog, analyse des gaps) pour éviter les doublons.
2. Carte route → garde générée depuis `create_app()`, puis relecture de chaque garde sensible jusqu'à `decide()` et `has_privilege()`.
3. Pour chaque suspicion, écriture d'un PoC pytest dans `c01/poc/` qui démontre le comportement actuel : le test passe tant que le défaut existe. Aucun fichier du dépôt n'a été modifié.
4. Les lignes des `locations` ont été relues directement dans les fichiers.

## Commandes lancées

```bash
cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . \
  ../docs/revue/audit-2026-09-29/c01/poc/ -q -p no:cacheprovider \
  --basetemp=<scratchpad>/ptN            # 9 passed
cd core && PYTHONPATH=. uv run python <scratchpad>/routes_map.py   # carte des routes
grep -rn "DATA_VIEW\b\|ANALYTICS_VIEW" core/app shell/src           # c01-010
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate \
  ../docs/revue/audit-2026-09-29/c01 --repo-root ..
```

Note : `--basetemp` est nécessaire parce que `/tmp/pytest-of-lenen` appartient à root sur ce poste.
