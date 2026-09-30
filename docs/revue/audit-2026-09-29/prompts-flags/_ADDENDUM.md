
## Passe complémentaire « flags allumés » (2026-09-30)

La première passe a tourné avec ETL, export, appexport, admin tools, quotas, tileset3d/terrain3d éteints ;
elle n'a donc pas pu exécuter ces capacités. Cette passe est rejouée sur une stack où elles sont **allumées**
(tout sauf LLM ; le profil `observability` est absent : le port hôte 3001 de Grafana est refusé par WSL2).
`CORE_SHARE_LINK_TOKEN_SECRET`, `CORE_EXPORT_TOKEN_SECRET` et `CORE_ADMIN_TOOLS_TOKEN_SECRET` sont définis ;
`CORE_QUOTA_MAX_ITEMS_PER_TENANT=100000`, `CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT=10000` (un test de blocage
de quota doit donc créer un tenant/limite de test ou le simuler, sans modifier la stack).

- **Ne re-teste pas ce qui a déjà été audité** : lis `docs/revue/audit-2026-09-29/<id sans b>/findings.jsonl` et `resume.md`
  et concentre-toi sur le « Non couvert » de cet agent. Références : `related_gap` = l'id d'origine quand tu confirmes ou
  réfutes un finding de première passe (ex. un `probable` par lecture de code).
- Tes findings et specs portent le préfixe de ton dossier (`<id>b-NNN`, `shell/e2e/journeys/<id>b/`). Budget : 25 tests.
- Les bugs connus restent valables (upload/alerte en 500 à cause d'`AppNotOpen`, worker MapLibre octet-stream, file `harvest` non consommée) :
  contourne-les comme les agents précédents (voir `shell/e2e/journeys/j03/seed.ts`, `j12/helpers.ts`).
- Ne modifie pas la stack. Si une capacité ne démarre pas malgré le flag, c'est un finding (vérifie `docker compose ps`/logs).
