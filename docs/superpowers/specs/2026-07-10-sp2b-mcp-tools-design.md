# GeoStudio SP-2b — Outils MCP (catalogue, config, partage)

> Design / spec. Seconde et dernière sous-phase de SP-2 (serveur MCP v0).
> SP-2a a posé l'authentification OAuth d'un `/mcp` sans aucun outil réel ;
> ce sous-plan y branche les capacités métier — miroir strict de l'API
> existante, rien de plus. Rend la démo « ouvre Claude, dis crée-moi un
> dashboard de suivi des incidents par commune, obtiens une app dans le
> catalogue » réelle (M2 « AI-operable » de la feuille de route).
>
> Date : 2026-07-10.
> Statut : design proposé.
> Prérequis : SP-2a livré — `/mcp` authentifié, `TokenVerifier`s, `whoami`.

---

## 1. Contexte et périmètre

La feuille de route (§SP-2) fixe déjà la liste des outils : `list_items`,
`get_item`, `get_app_config`, `save_app_config` (avec révision),
`create_item`, `get_sharing`/`set_sharing` — « c'est-à-dire strictement l'API
existante, ni plus ni moins de droits ». SP-2a a construit le tuyau
d'authentification (OAuth 2.1 + PKCE, DCR, audience `geostudio-mcp`,
résolution d'identité) mais n'a livré aucune capacité réelle (`whoami`
seulement). Ce sous-plan branche les 7 outils métier sur ce tuyau déjà
authentifié.

**Contenu.**
- 7 outils MCP (`list_items`, `get_item`, `get_app_config`,
  `save_app_config`, `create_item`, `get_sharing`, `set_sharing`) dans
  `core/app/mcp/tools.py`, réutilisant les mêmes fonctions de repository que
  les routes REST équivalentes — aucune logique métier dupliquée, `can()`
  reste l'unique porte d'autorisation.
- Publication des JSON Schema d'`AppConfig`/`MapConfig`
  (`BuilderConfig.model_json_schema()`, Pydantic) : une ressource MCP
  (`schema://app-config`) **et** un endpoint HTTP classique
  (`GET /schemas/app-config`) réutilisable hors MCP.
- `actor_kind=agent` dans `audit_log` pour toute action d'écriture MCP,
  mêmes noms d'action que leurs équivalents REST.

**Hors périmètre.**
- **Pilotage d'une app en cours d'exécution depuis un dialogue naturel**
  (filtrer, zoomer, etc.) — discuté en session et explicitement écarté :
  demanderait un canal temps réel cœur↔navigateur qui n'existe pas encore
  (l'état runtime d'une app — bus d'actions, widgets — vit côté shell,
  process navigateur, pas dans le cœur). Chantier architectural distinct, à
  brainstormer séparément une fois un mécanisme temps réel choisi ; ne pas
  le confondre avec la création/lecture de configs que ce sous-plan couvre.
- `listGroups`/gestion de groupes, upload de vignette, suppression d'item —
  pas dans la liste de la feuille de route, non ajoutés (discipline
  anti-scope-creep, cf. §7 Risques de la feuille de route pour SP-2).
- Historique de révisions / rollback exposés comme outils MCP — `save_app_config`
  crée une révision à chaque appel (comportement déjà automatique de
  `configs_repo.update_config`), mais lister/rollback les révisions via MCP
  n'est pas dans la liste de la feuille de route.

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Emplacement | `core/app/mcp/tools.py`, enregistrés sur le même `FastMCP` que SP-2a a monté à `/mcp`. `app.mcp` reste au sommet du layering, importe directement `app.items`/`app.configs`/`app.sharing`. |
| Implémentation des outils | Appellent les **fonctions de repository**, pas les routes REST elles-mêmes (mêmes fonctions que `app.public` réutilise déjà pour ses propres endpoints anonymes). |
| Autorisation | `can()` appelé exactement comme dans les routes REST — items/configs/sharing restent gardés par la même porte unique, aucune logique de visibilité parallèle pour l'agent. |
| Résolution d'identité / owner | Le `User` résolu par le `TokenVerifier` de SP-2a (même mécanisme que `whoami`) — `create_item` dérive toujours l'owner de cette identité, jamais d'un paramètre fourni par l'agent (même garantie que `POST /configs` côté REST depuis SP-1c). |
| Audit | Chaque outil d'écriture appelle `write_audit(..., actor_kind="agent", ...)` avec le même nom d'action que la route REST équivalente — un appel d'audit propre à l'outil, pas de refactor des routes REST existantes (qui restent `actor_kind="user"` partout ailleurs). |
| Schémas JSON | `BuilderConfig.model_json_schema()` exposé en ressource MCP (`schema://app-config`) et en endpoint HTTP (`GET /schemas/app-config`) — les deux dérivent du même modèle Pydantic, donc structurellement identiques par construction. |
| Erreurs | Une exception Python normale (`ValueError`, etc.) levée dans le corps d'un outil devient automatiquement une erreur d'outil MCP (`is_error=True`, message visible par l'agent) — confirmé par le SDK (`Tool.run()` capture toute exception et la re-lève en `ToolError`). Pas de mapping HTTP 404/403/422 à construire à la main ; le SDK n'a qu'une seule voie d'échec de toute façon (`raise MCPError` court-circuiterait en erreur *protocole*, invisible au modèle — donc jamais utilisé ici). |
| `save_app_config` / révisions | Comportement identique à `PUT /configs/by-item/{id}` : chaque appel crée une nouvelle révision automatiquement (déjà le comportement de `configs_repo.update_config`) ; pas de nouvel outil pour lister/rollback. |
| `list_items` / scope | Mêmes paramètres et sémantique que `GET /items` (SP-1c) : `q`, `type`, `scope` (`all`/`mine`/`shared`/`public`), `page`, `pageSize` — filtrage serveur réel, pas d'approximation côté agent. |

## 3. Les 7 outils

```
list_items(q?, type?, scope?, page?, pageSize?) -> ItemPage
  → items_repo.list_items (identique à GET /items)

get_item(itemId) -> Item
  → items_repo.get_access_facts + can(read) + items_repo.get_item
  → invisible (can(read) faux) : ValueError("item not found") → is_error

get_app_config(itemId) -> BuilderConfig
  → items_repo.get_access_facts + can(read) + configs_repo.get_config_by_item

save_app_config(itemId, config: BuilderConfig) -> ConfigRead
  → items_repo.get_access_facts + can(write) + configs_repo.update_config
  → write_audit(action="config.update", actor_kind="agent")

create_item(kind: "app"|"dashboard", title, config: BuilderConfig) -> Item
  → configs_repo.create_config + items_repo.create_item
  → owner = identité résolue (jamais un paramètre d'outil)
  → write_audit(action="item.create", actor_kind="agent")
  → write_audit(action="config.create", actor_kind="agent")

get_sharing(itemId) -> Sharing
  → items_repo.get_access_facts + can(read) + sharing_repo.list_shares

set_sharing(itemId, sharing: Sharing) -> None
  → items_repo.get_access_facts + can(share) + sharing_repo.replace_shares
  → write_audit(action="item.share", actor_kind="agent")
```

Chaque outil qui prend un `itemId` suit exactement la règle 404/403 déjà en
place côté REST (SP-1c) : invisible en lecture → erreur d'outil signifiant
« introuvable » ; visible mais action refusée → erreur d'outil signifiant
« non autorisé ». Le message d'erreur ne distingue pas plus finement (pas de
code structuré), cohérent avec la décision §2 (une exception suffit).

## 4. Schémas JSON

```python
@mcp.resource("schema://app-config")
def app_config_schema() -> dict:
    """JSON Schema d'AppConfig — à valider avant create_item/save_app_config."""
    return BuilderConfig.model_json_schema()
```

```
GET /schemas/app-config → même dict, servi en HTTP classique (hors MCP,
                           réutilisable par tout outillage externe)
```

Une seule source de vérité (`BuilderConfig`, déjà existant depuis SP-0) — la
ressource MCP et l'endpoint HTTP ne sont que deux façons de lire le même
schéma, jamais deux schémas à maintenir en synchronisation manuelle.

## 5. Gestion d'erreurs

- Item invisible en lecture → `ValueError` dans l'outil → erreur d'outil MCP
  (`is_error=True`), message générique (anti-énumération, cohérent avec la
  règle 404 déjà en place côté REST).
- Item visible mais action refusée (`can(write)`/`can(share)` faux) →
  `ValueError` distinct (message différent, mais toujours une erreur d'outil
  MCP standard, pas un code HTTP à mapper).
- `config` invalide (ne correspond pas au schéma `BuilderConfig`) → la
  validation Pydantic échoue avant même d'atteindre le repository — remonte
  déjà comme une erreur d'outil via le mécanisme de validation d'arguments
  du SDK (`fn_metadata.call_fn_with_arg_validation`), pas un cas à gérer à la
  main.
- `create_item` avec un `owner` fourni par l'agent : ignoré silencieusement
  si le paramètre existe dans l'outil (il ne devrait même pas exister dans
  sa signature — l'owner n'est jamais un paramètre d'entrée de `create_item`,
  contrairement à l'ancien `POST /configs` d'avant SP-1c qui l'acceptait et
  a été corrigé pour cette même raison).

## 6. Stratégie de tests

- **Matrice `can()` par outil** (même discipline que SP-1c) : pour
  `get_item`/`get_app_config`/`save_app_config`/`get_sharing`/`set_sharing`,
  rejouer owner/group-viewer/group-editor/stranger × read/write/share, via
  le client MCP in-memory du SDK (`mcp.Client`), pytest pur.
- **`create_item` ne permet jamais de spoofer l'owner** : test dédié,
  l'item créé appartient toujours à l'identité résolue du token.
- **`actor_kind=agent`** : un test par outil d'écriture vérifiant la ligne
  `audit_log` (action + `actor_kind="agent"`, pas `"user"`).
- **Schémas JSON** : la ressource MCP et l'endpoint HTTP renvoient un JSON
  Schema structurellement identique, qui valide bien un `AppConfig`/
  `MapConfig` réel existant en base.
- **Erreurs métier → erreur d'outil MCP** : un item invisible fait échouer
  l'outil (`is_error=True`), pas un succès silencieux ni un crash serveur.
- **Vérification manuelle documentée** (README, même format que
  SP-1d.2/SP-2a) : un vrai client MCP (ou l'inspecteur MCP) exécute le
  scénario complet de la feuille de route — lister les items, lire une
  config, **créer un dashboard qui s'ouvre réellement dans le builder du
  shell** — seul moyen de vérifier le critère produit final de bout en
  bout, pas juste l'API.

## 7. Critères d'acceptation

- Un client MCP standard liste les items, lit une config, crée un dashboard
  valide (validé par le schéma publié) qui s'ouvre dans le builder du shell.
- Chaque outil respecte exactement les mêmes limites d'autorisation que la
  route REST équivalente — ni plus, ni moins.
- Toute action d'écriture via MCP apparaît dans `audit_log` avec
  `actor_kind=agent` et le même nom d'action que son équivalent REST.
- Un agent ne peut jamais créer un item pour le compte d'un autre
  utilisateur.

## 8. Risques

Risque principal (identique à SP-2a et déjà nommé par la feuille de route) :
le scope creep — « et si l'agent pouvait aussi… ». Discuté explicitement en
session pour le pilotage runtime d'une app (filtrer/zoomer en langage
naturel) et écarté du périmètre : ce n'est pas une extension mineure de la
liste d'outils, mais un problème architectural différent (canal temps réel
cœur↔navigateur inexistant), qui mérite son propre brainstorm plutôt que
d'être glissé dans ce sous-plan.

Risque technique : dupliquer les appels `can()`/`write_audit` dans les
outils au lieu de les réutiliser depuis les routes REST crée une deuxième
surface à maintenir en cohérence avec la première si `can()` évolue —
acceptable en v0 (la duplication porte sur des appels de 1-2 lignes, pas sur
la logique de `can()` elle-même, qui reste unique), mais à surveiller si SP-7
(MCP v1) ajoute des outils supplémentaires du même acabit.
