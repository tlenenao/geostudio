# SP-7 — Recherche sémantique + MCP v1 : design

**Date** : 2026-07-13
**Statut** : validé (brainstorm), prêt pour plan d'implémentation

## Contexte

SP-7 (feuille de route, `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
§SP-7) dépend de SP-2 (serveur MCP v0) et SP-6 (ingestion) — tous deux clos.
C'est le plus petit SP de la route (25–45 h). Deux morceaux fortement
couplés, traités dans une seule spec (MCP v1 réutilise directement le moteur
de recherche) :

1. **Recherche sémantique du catalogue** : pgvector, embeddings enfichables,
   recherche hybride (texte + vecteur) sur la barre de recherche existante.
2. **MCP v1** : trois nouveaux outils — `search_catalog`, `query_features`,
   `create_form_app`.

État vérifié du code actuel (2026-07-13) :

- La recherche d'items (`list_items`, `core/app/items/repository.py:75`) fait
  un `ILIKE '%q%'` sur `title`/`abstract`, sans les `keywords` (champ JSON
  déjà présent sur `Item` mais jamais utilisé en recherche).
- `LayerPicker` (`shell/src/map/LayerPicker.tsx`) liste toutes les sources
  sans aucune recherche ; `listLayerSources()` (`ItemClient`) ne prend aucun
  paramètre.
- Aucune notion de colonnes/champs par défaut n'existe : le widget Table
  affiche les propriétés du premier enregistrement chargé si `columns` est
  vide (fallback d'affichage, pas une sélection persistée) ; le widget
  Formulaire mappe *tous* les champs du schéma 1:1 via `fieldsFromSchema()`
  (`shell/src/builder/widgets/form.tsx:25`), sans logique de masquage par
  défaut au-delà des types `unsupported`. `id`/géométrie sont déjà exclus de
  `schema.fields` côté serveur (`get_collection_schema`,
  `core/app/collections/routes.py:~222`) — pas une exclusion à réinventer.
- Le gabarit de galerie « Application de saisie » (SP-4c,
  `shell/src/builder/templates.ts`) pré-câble Formulaire+Carte+Table avec la
  messagerie `itemSelected → loadRecord`, mais `fields`/`columns` y sont
  seedés vides — un humain doit toujours cliquer « Charger les champs du
  schéma » et taper les noms de colonnes.
- Les 7 outils MCP existants (SP-2b) sont de minces adaptateurs au-dessus des
  mêmes fonctions de repository que l'API REST, avec la même porte `can()` et
  `actor_kind=agent` dans `audit_log` — c'est le patron à reproduire.

## Objectif

Le catalogue se cherche en langage naturel, même sans mot-clé exact ; un
agent MCP peut chercher, lire des données géospatiales, et composer une
application formulaire fonctionnelle sur une collection existante — sans
qu'un humain n'ouvre le builder.

## Hors périmètre

- Catalogue STAC complet, DCAT, moissonnage (SP-12).
- Toute UI de recherche en dehors de la barre catalogue existante et du
  nouveau champ de recherche `LayerPicker` (pas de refonte de navigation).
- Ré-embedding en masse au changement de fournisseur/modèle (à faire à la
  main via un script one-shot si besoin réel — pas un critère d'acceptation
  de SP-7).
- Qualité sémantique des `FakeProvider` en E2E navigateur : les specs
  Playwright vérifient le *mécanisme* (le pipeline hybride s'exécute, ne
  casse pas la recherche substring existante, respecte les permissions) ; la
  pertinence sémantique elle-même est vérifiée par des tests cœur (pytest)
  avec un provider à vecteurs contrôlés (voir Tests).
- `search_catalog` ne couvre pas les collections (voir Architecture MCP) —
  seul `/collections?q=` (REST, consommé par `LayerPicker`) les cherche.

## Architecture — recherche hybride

### Stockage

Colonne `embedding vector(1536) NULL` ajoutée directement sur `items` et sur
`collections` (migration Alembic : `CREATE EXTENSION IF NOT EXISTS vector`,
`CREATE EXTENSION IF NOT EXISTS pg_trgm`). Choix d'une colonne directe plutôt
qu'une table d'embeddings polymorphique séparée : suit le patron déjà
utilisé pour `feature_count` (SP-6c) sur `Collection`, pas de lignes
orphelines à nettoyer à la suppression (la colonne disparaît avec la ligne),
pas de jointure supplémentaire dans les requêtes de recherche déjà
existantes. 1536 dimensions = défaut compatible OpenAI
`text-embedding-3-small`/Voyage, dimension fixée par la migration (changer
de dimension = nouvelle migration + ré-embedding complet, documenté comme
opération manuelle hors périmètre).

Index : GIN trigram sur `title || ' ' || abstract` (items) et
`title || ' ' || description` (collections) ; index ANN (`ivfflat`, distance
cosine) sur `embedding` des deux tables.

### Fournisseur d'embeddings (enfichable)

`core/app/search/providers.py` :

```python
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...
```

- `OpenAICompatibleProvider` : appel HTTP `POST {CORE_EMBEDDING_API_URL}`
  avec `CORE_EMBEDDING_API_KEY`/`CORE_EMBEDDING_MODEL` — compatible
  OpenAI/Voyage sans code spécifique à un fournisseur.
- `FakeProvider` : déterministe par défaut (hash SHA-256 du texte → graine
  d'un vecteur 1536-d), zéro appel réseau. Actif par défaut en dev/test/mock
  (`CORE_EMBEDDING_PROVIDER=fake`, même convention que `CORE_AUTH_MODE=mock`
  côté shell). Accepte aussi une table `text → vector` explicite injectée en
  test (pas seulement le hash) pour permettre aux tests cœur de contrôler
  la similarité et vérifier le ranking RRF de façon déterministe.

Sélection du provider par variable d'env au démarrage du cœur et du worker
(même mécanisme, un seul provider actif à la fois — pas de bascule à chaud).

### Pipeline d'embedding

Un job procrastinate `embed_item`/`embed_collection` est enqueue après
chaque `create`/`update` d'item ou de collection (asynchrone, cohérent avec
le patron d'ingestion de SP-6a — jamais de blocage de l'écriture, jamais
d'exception réseau qui remonte à l'utilisateur). Texte vectorisé :
- item : `title + "\n" + abstract + "\n" + ", ".join(keywords)`
- collection : `title + "\n" + description`

Le job échoue proprement (log, pas de retry infini) si le provider est
indisponible ; l'item/la collection reste cherchable par trigram seul en
attendant (dégradation gracieuse, pas de champ `embedding` = recherche
texte seule pour cette ligne).

### Recherche hybride + permissions

Dans `list_items`/`list_collections` (nouveau, symétrique) :

1. Le filtre `can()`/scope existant (owner/public/shared/all, RLS le cas
   échéant) réduit l'ensemble candidat **avant** tout scoring — comme
   aujourd'hui. Aucune requête de recherche ne s'exécute sur des lignes
   invisibles à l'appelant.
2. Sur cet ensemble déjà filtré : une requête trigram (`similarity()` >
   seuil, top-K) et, si `q` est non vide, une requête vectorielle (embedding
   de `q` calculé synchrone via le provider — un seul appel court, pas de
   job — puis tri par distance cosine, top-K).
3. **Reciprocal Rank Fusion** : `score(doc) = Σ 1/(60 + rang_i)` sur les
   listes où `doc` apparaît (constante `k=60`, valeur standard documentée
   pour RRF). Un document présent dans une seule liste est classé sur ce
   seul score — pas de pénalité pour absence de l'autre signal. Choisi
   plutôt qu'une somme pondérée de scores normalisés : pas de poids
   arbitraire à calibrer, robuste si le vecteur est absent (embedding pas
   encore calculé) ou si `q` est vide (fallback trigram/tri par date pur,
   comportement actuel inchangé).
4. Si `q` est vide : comportement actuel inchangé (tri par `created_at`
   desc), zéro changement perçu pour un parcours catalogue sans recherche.

`GET /collections` gagne le paramètre `q?` (même pipeline, même RRF).
`listLayerSources(params?: { q?: string })` côté `ItemClient` prend le
paramètre optionnel ; `LayerPicker` gagne un champ de recherche texte
(debounced) au-dessus de la liste.

## Architecture — MCP v1

Trois outils ajoutés au serveur MCP existant (`core/app/mcp/`), même
authentification (token utilisateur), même `actor_kind=agent` dans
`audit_log` que les 7 outils v0.

### `search_catalog(q, type?, scope?, page, pageSize)`

Mince adaptateur au-dessus de `list_items` avec le nouveau ranking hybride —
**items seulement**, pas les collections. Choix délibéré : garder le
périmètre MCP v0/v1 strictement aligné sur « miroir de l'API existante »
(déjà la discipline de SP-2, où le risque nommé était le scope creep) ; les
collections restent un concept navigué via le builder/`LayerPicker`, pas via
le catalogue MCP en v1.

### `query_features(collectionId, bbox?, filters?, page, pageSize)`

Même capacités que `GET /collections/{id}/items` (OGC API Features déjà en
place depuis SP-3b) : bbox, filtres par champ, pagination, mêmes fonctions
de repository, mêmes permissions (RLS + `can()`). Pas de traduction
langage-naturel→filtre : l'agent passe des filtres structurés, comme
n'importe quel client OGC.

### `create_form_app(collectionId, title?)`

1. Introspecte le schéma (`get_collection_schema`, réutilisé en interne).
2. Calcule `canWrite` pour l'utilisateur/agent courant — même prédicat
   serveur que celui exposé sur les collections depuis SP-4c
   (`_get_writable`).
3. Génère un `AppConfig` :
   - **Table** : `columns` = tous les champs de `schema.fields` (géométrie
     et `pk` déjà exclus par l'introspection serveur — aucune heuristique de
     pertinence à inventer).
   - **Carte** : couche sur la collection, style par défaut (même logique
     que l'ingestion SP-6a/b).
   - **Formulaire** : inclus **seulement si `canWrite`** ; champs générés
     par un mapping schéma→champs équivalent à `fieldsFromSchema` (TS,
     `shell/src/builder/widgets/form.tsx:25`) mais réimplémenté côté Python
     (`core/app/mcp/form_app.py`) — même règle d'exclusion (`type !=
     "unsupported"`), tous les autres champs visibles, non requis sauf
     contrainte du schéma. Si `canWrite` est faux : app Carte+Table seule
     (lecture), pas de Formulaire même masqué — cohérent avec « pas de
     widget inutile dans une config générée par un agent ».
   - Même câblage `itemSelected → loadRecord` que le gabarit « Application
     de saisie » (SP-4c) entre Table/Carte et Formulaire.
4. `create_item` + `save_app_config` (mêmes fonctions que les outils MCP v0
   existants), retourne l'id de l'item créé.

**Point d'attention documenté, pas de solution parfaite en v1** : le mapping
schéma→champs existe maintenant en deux implémentations (TS pour le builder
humain, Python pour `create_form_app`) — même risque de dérive que CEL
(cel-js/cel-python, arbitrage A8). Mitigation : un test de non-régression
structurel (une fixture de schéma fixe → comparaison de la *forme* des
champs générés des deux côtés, pas un partage de code prématuré entre un
front TS et un cœur Python).

## Tests

- **Cœur (pytest)** : `FakeProvider` à vecteurs explicites pour prouver le
  RRF (un document textuellement éloigné mais vectoriellement proche doit
  sortir devant un document avec un match trigram faible) ; permissions
  (un item privé d'un autre tenant/utilisateur n'apparaît jamais, même
  proche sémantiquement) ; dégradation gracieuse (embedding NULL = recherche
  trigram seule, pas d'exception) ; `create_form_app` avec/sans `canWrite` ;
  `query_features` parité de permissions avec l'endpoint REST existant.
- **Shell (vitest)** : `LayerPicker` avec le champ de recherche (debounce,
  état vide, erreur) ; `listLayerSources({ q })` dans `itemClient.test.ts`.
- **E2E (Playwright)** : la barre de recherche catalogue continue de trouver
  un item par sous-chaîne du titre (non-régression du comportement actuel) ;
  un item privé d'un autre utilisateur n'apparaît jamais dans les résultats
  même en tapant un terme proche ; nouvelle spec `layer-picker-search.spec.ts`
  pour la recherche de collections. Les 19 specs existantes restent vertes.
  La *pertinence sémantique* proprement dite n'est pas testée en E2E
  navigateur (voir Hors périmètre) — c'est le rôle des tests cœur avec
  vecteurs contrôlés.

## Critères d'acceptation (repris/précisés de la feuille de route)

- « incidents voirie 2026 » trouve le bon dashboard même sans le mot exact
  dans le titre (test cœur avec `FakeProvider` à vecteurs contrôlés reproduisant
  ce scénario).
- Un agent MCP compose une app formulaire fonctionnelle sur une collection
  existante via `create_form_app`, qui s'ouvre dans le builder du shell.
- Un `viewer` sans droit d'écriture obtient via `create_form_app` une app
  Carte+Table sans Formulaire ; le serveur refuserait de toute façon
  l'écriture si le Formulaire était forcé (défense en profondeur inchangée).
- Recherche par sous-chaîne exacte (comportement actuel) non régressée.
- Aucune fuite de metadata d'un item/collection non-visible dans le
  classement de recherche (testé E2E + pytest).
- `LayerPicker` trouve une collection par un terme proche de son titre/
  description sans correspondance exacte.
