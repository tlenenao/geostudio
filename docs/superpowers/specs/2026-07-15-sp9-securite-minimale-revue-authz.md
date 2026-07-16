# SP-9 — Sécurité minimale : revue authz

Méthode : pour chaque endpoint/outil ci-dessous, vérifié dans son/ses
fichier(s) de test associé(s) l'existence d'un test couvrant : accès
autorisé (owner/partage), accès refusé (non-owner sans partage → 403/404
selon la convention déjà en place), accès anonyme si la route/l'outil le
permet, et — pour les modules ajoutés depuis SP-7/SP-8b/SP-8c (extensions,
recherche sémantique) — l'isolation cross-tenant.

Convention de lecture : « Oui » = un test existant (ou ajouté par cette
revue, marqué *) exerce réellement ce critère. « N/A » = le critère ne
s'applique pas à cet endpoint (ex. une route de création n'a pas de cible à
« refuser », une route qui exige toujours l'authentification n'a pas de
scénario anonyme pertinent). « Non testé (structurel) » = le comportement
est protégé par construction (filtre `tenant_id` dans la requête du
repository, même garde qu'un endpoint voisin déjà testé) mais aucun test
dédié ne l'exerce isolément — documenté, pas ouvert comme trou faute de
budget pour épuiser toutes les permutations.

## `auth/routes.py`

| Endpoint | Autorisé ? | Refusé (403/404) ? | Anonyme (si applicable) ? | Cross-tenant (si applicable) ? | Trou ? |
|---|---|---|---|---|---|
| `GET /me` | Oui (`test_me.py`) | N/A | N/A (401, hors périmètre authz) | N/A (renvoie l'identité de l'appelant) | Non |
| `GET /users` | Oui (`test_users_admin_routes.py`) | Oui (403 non-admin) | N/A | Non testé (structurel — filtré par `tenant_id` en repo) | Non |
| `PATCH /users/{id}` | Oui | Oui (403 non-admin, 404 inconnu, 409 dernier admin) | N/A | **Oui\*** (`test_patch_user_cross_tenant_returns_404`, ajouté) | Non (couverture ajoutée) |

## `collections/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `POST /collections` | Oui | Oui (403 non-admin) | N/A | N/A (création) | Non |
| `GET /collections` | Oui | N/A (liste filtrée, pas de 403) | Oui (`test_public_collection_visible_to_anonymous`) | Non testé isolément (structurel, cf. `test_collections_repository.py` + pattern extensions) | Non |
| `GET /collections/candidates` | Oui (admin) | Oui (403 non-admin) | N/A | Oui (`test_candidates_real_introspection_and_tenant_isolation`) | Non |
| `GET /collections/{id}` | Oui | Oui (404 privée) | Oui | Non testé isolément (même garde `get_readable_collection` que `/candidates`) | Non |
| `GET /collections/{id}/schema` | Oui | Non testé isolément (partage `get_readable_collection`, déjà éprouvée par `get_collection`) | Non testé isolément | Non testé isolément | Non (documenté) |
| `PATCH /collections/{id}` | Oui | **Oui\*** (`test_patch_by_non_owner_without_editor_role_returns_403`, ajouté) | N/A | Non testé isolément | Non (couverture ajoutée — trou de couverture réel, cf. §Trous) |
| `DELETE /collections/{id}` | Oui | Oui (403 non-admin) | N/A | Non testé isolément | Non |
| `GET /collections/{id}/sharing` | Oui | **Oui\*** (`test_get_sharing_requires_owner_or_admin`, ajouté) | N/A | Non testé isolément | Non (couverture ajoutée — trou de couverture réel) |
| `PUT /collections/{id}/sharing` | Oui | Oui (403) | N/A | Oui (groupe d'un autre tenant → 404) | Non |

## `configs/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `POST /configs` | Oui | N/A (création) | Oui (401 sans en-tête, mode réel) | N/A | Non |
| `GET /configs/{id}` | Oui | Oui (404 stranger même tenant) | N/A | Non testé isolément (delete seul testé cross-tenant) | Non |
| `PUT /configs/{id}` | Oui | Oui (404 stranger, 403 group viewer) | N/A | Non testé isolément | Non |
| `GET /configs/{id}/revisions` | Oui | Oui (404 stranger) | N/A | Non testé isolément | Non |
| `POST /configs/{id}/rollback` | Oui | Oui (404 stranger) | N/A | Non testé isolément | Non |
| `DELETE /configs/{id}` | Oui | Oui (404 stranger) | N/A | Oui (`test_delete_config_cross_tenant_returns_404_and_leaves_data_intact`) | Non |
| `GET /configs/by-item/{id}` | Oui | Oui (404 stranger) | N/A | Non testé isolément | Non |
| `PUT /configs/by-item/{id}` | Oui | Non testé isolément (couvert par le même code que `PUT /configs/{id}`) | N/A | Non testé isolément | Non (documenté) |
| `DELETE /configs/by-item/{id}` | Oui | Oui | N/A | Oui (cross-tenant) | Non |
| `DELETE /items/{item_id}` | Oui | Oui | N/A | Oui (cross-tenant) | Non |

## `items/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `GET /items` | Oui | N/A (liste filtrée — permission-filter-avant-scoring prouvé à l'échelle du repository, `test_items_repository.py::test_list_items_scope_shared_and_all` + `test_list_items_hybrid_search_never_leaks_an_invisible_item`) | N/A | N/A | Non |
| `GET /items/{id}` | Oui | Oui (404 non-owner, 200 group viewer) | N/A | N/A (structurel) | Non |
| `PATCH /items/{id}` | Oui | Oui (404 non-owner, 403 group viewer) | N/A | N/A | Non |
| `POST /items/{id}/thumbnail` | Oui | Oui (404 non-owner) | N/A | N/A | Non |
| `GET /items/{id}/thumbnail` | Oui | Non testé isolément pour non-owner (même garde read que `get_item`, déjà éprouvée ; seul le 404 « pas de miniature » est testé) | N/A | N/A | Non (documenté) |
| `GET /items/{id}/sharing` | Oui | Oui (404 non-owner) | N/A | N/A | Non |
| `PUT /items/{id}/sharing` | Oui | Oui (403 group viewer) | N/A | N/A | Non |

## `features/routes.py` (OGC API Features)

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `GET /` | N/A | N/A | Oui | N/A | Non |
| `GET /conformance` | N/A | N/A | Oui | N/A | Non |
| `GET /collections/{id}/items` | Oui | Oui (404 anonyme sur collection privée) | Oui | N/A (partage `get_readable_collection`) | Non |
| `GET /collections/{id}/items/{fid}` | Oui | Oui (404 feature inconnue) ; refus de collection non testé isolément | Non testé isolément | N/A | Non (documenté) |
| `POST /collections/{id}/items` | Oui (editor) | Oui (403 viewer public ; **404 privée non-partagée, ajouté**) | Oui (401 sans auth) | N/A | Non (couverture ajoutée) |
| `PUT /collections/{id}/items/{fid}` | Oui | **Oui\*** (404 privée, ajouté) | N/A | N/A | Non (couverture ajoutée) |
| `DELETE /collections/{id}/items/{fid}` | Oui | **Oui\*** (404 privée, ajouté) | N/A | N/A | Non (couverture ajoutée) |

## `ingestion/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `POST /uploads/presign` | Oui | N/A | N/A (nécessite auth) | N/A | Non |
| `POST /uploads/inspect` | Oui | Oui (400 préfixe clé d'un autre tenant) | N/A | Oui (confused-deputy guard) | Non |
| `POST /uploads` | Oui | Oui (400 préfixe clé d'un autre tenant) | N/A | Oui | Non |
| `GET /uploads/{job_id}` | Oui | Oui (404 job inconnu) | N/A | **Oui\*** (`test_get_upload_job_cross_tenant_returns_404`, ajouté) | Non (couverture ajoutée) |

## `sharing/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `GET /groups` | Oui | N/A (filtré par tenant) | N/A | Non testé isolément (structurel) | Non |
| `POST /groups` | Oui | N/A (création) | N/A | N/A | Non |
| `POST /groups/{id}/members` | Oui | Oui (404 non-créateur, 404 groupe inconnu) | N/A | Oui (`test_add_member_cross_tenant_user_returns_404`) | Non |

## `public/routes.py` (accès anonyme)

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `GET /public/items/{id}` | Oui (publié) | Oui (404 non publié / inexistant) | Oui (intrinsèque) | N/A par conception — un item publié est volontairement global, sans frontière de tenant (`get_published_item` ne filtre pas par `tenant_id`, cohérent avec la sémantique « publié = public à l'échelle de l'instance ») | Non |
| `GET /public/configs/by-item/{id}` | Oui | Oui | Oui | N/A (idem) | Non |

## `extensions/routes.py`

| Endpoint | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `POST /extensions` | Oui | Oui (403 non-admin) | N/A | N/A (création) | Non |
| `PATCH /extensions/{id}` | Oui | Oui (403 non-admin) | N/A | **Oui\*** (`test_patch_extension_cross_tenant_returns_404`, ajouté) | Non (couverture ajoutée) |
| `GET /extensions` | Oui | N/A (liste filtrée) | Oui (`test_get_extensions_is_anonymous_and_scoped_to_default_tenant`) | Oui (`test_get_extensions_never_leaks_across_tenants` + `all=true` × 3 combinaisons) | Non |

## Outils MCP (`app/mcp/tools.py`)

| Outil | Autorisé ? | Refusé ? | Anonyme ? | Cross-tenant ? | Trou ? |
|---|---|---|---|---|---|
| `whoami` | Oui | N/A | N/A (MCP toujours authentifié) | N/A | Non |
| `list_items` | Oui | N/A (liste filtrée, même repo que `GET /items`) | N/A | N/A (structurel) | Non |
| `search_catalog` | Oui | N/A | N/A | N/A | Non |
| `query_features` | Oui | **Oui\*** (`test_query_features_on_private_unshared_collection_errors`, ajouté) | N/A | N/A (partage `get_readable_collection`) | Non (couverture ajoutée) |
| `get_item` | Oui | Oui (`test_get_item_invisible_to_a_stranger_errors`) | N/A | N/A | Non |
| `get_app_config` | Oui | Non testé isolément (même garde `_require_access` que `get_item`/`save_app_config`, déjà éprouvée) | N/A | N/A | Non (documenté) |
| `save_app_config` | Oui | Oui (`test_save_app_config_by_group_viewer_errors`) | N/A | N/A | Non |
| `create_item` | Oui | N/A (création, owner forcé au caller) | N/A | N/A | Non |
| `create_form_app` | Oui | Oui (non-owner sans write → Formulaire omis ; collection inconnue → erreur) | N/A | N/A | Non |
| `get_sharing` | Oui | **Oui\*** (`test_get_sharing_invisible_to_a_stranger_errors`, ajouté) | N/A | N/A | Non (couverture ajoutée) |
| `set_sharing` | Oui | **Oui\*** (`test_set_sharing_by_group_viewer_errors`, ajouté ; + 404 groupe inconnu déjà présent) | N/A | N/A | Non (couverture ajoutée) |

## Recherche sémantique (SP-7, transverse)

| Composant | Testé ? |
|---|---|
| `reciprocal_rank_fusion` (scoring pur) | Oui (`test_search_ranking.py`) |
| `hybrid_search_ids` — filtre de permission AVANT scoring | Oui — `test_items_repository.py::test_list_items_hybrid_search_never_leaks_an_invisible_item` et `test_collections_repository.py::test_list_visible_collections_hybrid_search_never_leaks_an_invisible_collection` (fichiers non listés nommément par le brief mais directement responsables de cette garantie) |
| Fournisseur d'embeddings | Oui (`test_search_providers.py`) |

## Trous trouvés et corrigés

Aucun trou de **comportement** (aucun test rouge n'a révélé un `200`/`204` là
où un `403`/`404` était attendu). Le code lu à chaque étape confirmait déjà
la bonne garde avant l'écriture du test ; les 9 tests ajoutés ont tous
**passé du premier coup** — ce sont des trous de **couverture** sur un
comportement déjà correct, pas des failles de sécurité réelles.

1. **`PATCH /collections/{id}` — aucun test du 403 « write access required »**
   (`app/collections/routes.py:290`). `test_patch_and_delete` n'exerçait que
   la garde `DELETE` (`_require_admin`, un tout autre contrôle). Ajouté :
   `tests/test_collections_routes.py::test_patch_by_non_owner_without_editor_role_returns_403`.
   Repro avant écriture (le test n'existait pas — vérifié en le lançant une
   fois écrit) :
   `uv run pytest tests/test_collections_routes.py::test_patch_by_non_owner_without_editor_role_returns_403 -v`
   → `PASSED` du premier coup (comportement déjà correct).

2. **`GET /collections/{id}/sharing` — aucun test du 403 `_require_share`**
   sur la lecture (seul le `PUT` était couvert par
   `test_sharing_requires_owner_or_admin`). Ajouté :
   `tests/test_collections_sharing_routes.py::test_get_sharing_requires_owner_or_admin`.
   → `PASSED` du premier coup.

3. **`PATCH /users/{id}` — aucun test cross-tenant.** Un admin d'un tenant
   pourrait en théorie promouvoir/rétrograder un utilisateur d'un autre
   tenant en devinant son id ; le code filtre déjà par `tenant_id`
   (`app/auth/routes.py:74`) mais ce n'était pas exercé. Ajouté :
   `tests/test_users_admin_routes.py::test_patch_user_cross_tenant_returns_404`.
   → `PASSED` du premier coup.

4. **Écriture de features (`POST`/`PUT`/`DELETE /collections/{id}/items…`) —
   aucun test du cas « non-owner ne peut même pas lire » (404-avant-403).**
   Seul le cas « peut lire (public) mais pas écrire » (403) était couvert.
   Ajouté : `tests/test_features_routes_write.py::test_non_owner_write_on_private_collection_is_404_not_403`.
   → `PASSED` du premier coup (confirme que `_get_writable` appelle bien
   `get_readable_collection` avant le contrôle d'écriture,
   `app/features/routes.py:155-162`).

5. **`GET /uploads/{job_id}` — aucun test cross-tenant** (seul le job
   inconnu était testé). Ajouté :
   `tests/test_ingestion_routes.py::test_get_upload_job_cross_tenant_returns_404`.
   → `PASSED` du premier coup (`repo.get_job` filtre déjà par `tenant_id`,
   `app/ingestion/repository.py:27-32`).

6. **`PATCH /extensions/{id}` — aucun test cross-tenant** (seul `GET
   /extensions` avait `test_get_extensions_never_leaks_across_tenants`).
   Le brief appelle explicitement ce module comme nécessitant une couverture
   cross-tenant (ajouté depuis SP-8c). Ajouté :
   `tests/test_extensions_routes.py::test_patch_extension_cross_tenant_returns_404`.
   → `PASSED` du premier coup.

7. **Outil MCP `get_sharing` — aucun test de refus** (tous les tests
   existants appellent l'outil sur un item possédé par `mock_user`). Ajouté :
   `tests/test_mcp_tools_sharing.py::test_get_sharing_invisible_to_a_stranger_errors`.
   → `PASSED` du premier coup.

8. **Outil MCP `set_sharing` — aucun test de refus pour un rôle
   insuffisant** (seul le groupe inconnu était testé). Ajouté :
   `tests/test_mcp_tools_sharing.py::test_set_sharing_by_group_viewer_errors`.
   → `PASSED` du premier coup.

9. **Outil MCP `query_features` — aucun test sur une collection privée non
   partagée** (tous les tests existants utilisent une collection publique).
   Ajouté :
   `tests/test_mcp_tools_query_features.py::test_query_features_on_private_unshared_collection_errors`
   (marqué `postgis`, comme le reste du fichier). → `PASSED` du premier coup,
   validé contre un vrai PostGIS jetable (cf. rapport de tâche pour le détail
   de l'infra utilisée).

## Points documentés, non ouverts comme trous (hors budget de cette revue)

Ces cas partagent tous une garde déjà éprouvée ailleurs dans le même fichier
ou par le même helper (`get_readable_collection`, `_require_access`), ou sont
protégés par construction (filtre `tenant_id` dans la requête du
repository) sans qu'un test dédié à CE endpoint précis existe :

- `GET /users` et `GET /groups` : isolation cross-tenant non testée
  isolément pour le simple listing (structurelle, `tenant_id` de la requête).
- `GET /collections/{id}/schema`, `GET /collections/{id}` : cross-tenant non
  testé isolément (même garde que `/candidates`, qui lui l'est).
- `GET /configs/{id}`, `PUT /configs/{id}`, `GET /configs/{id}/revisions`,
  `POST /configs/{id}/rollback`, `GET /configs/by-item/{id}`,
  `PUT /configs/by-item/{id}` : cross-tenant non testé isolément (seules les
  3 variantes `DELETE` le sont) — module antérieur à SP-7/SP-8b/SP-8c, hors
  du périmètre cross-tenant explicitement demandé par le brief.
- `GET /items/{id}/thumbnail`, `GET /collections/{id}/items/{fid}`,
  outil MCP `get_app_config` : refus non testé isolément pour un objet non
  lisible (même garde read que l'endpoint/l'outil voisin, déjà éprouvée).

Aucun de ces points n'a révélé, lors de la lecture du code source
correspondant, une garde manquante ou incorrecte — ce sont des choix
d'arbitrage sur la profondeur de cette revue (temps fini, ~44 endpoints/
outils), pas des trous de sécurité identifiés et laissés ouverts.

## Conclusion

**0 trou de sécurité réel trouvé.** 9 trous de **couverture** trouvés et
comblés (tests ajoutés dans les fichiers existants les plus proches, jamais
de nouveau fichier) ; les 9 tests passent tous, et l'ensemble de la suite
(`uv run pytest`) passe sans régression : 395 passed / 65 skipped (sans
`CORE_TEST_DATABASE_URL`), 460 passed / 0 skipped (validé réellement contre
un PostGIS+pgvector jetable). `uv run lint-imports` reste clean (aucune
modification de ce plan ne touche les frontières de modules — seuls des
fichiers de test ont été modifiés).
