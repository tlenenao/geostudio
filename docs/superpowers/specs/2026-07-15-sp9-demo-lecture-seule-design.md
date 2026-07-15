# SP-9 — Mode démo lecture seule (produit) : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormée le
> 2026-07-15, en même temps que le reste de SP-9 — planifiable et exécutable
> indépendamment, comme `2026-07-13-sp9-gestion-collections-design.md`.
>
> **Périmètre décidé avec l'utilisateur** : cette spec couvre uniquement le
> comportement produit du mode lecture seule (cœur + shell). L'hébergement
> réel de la démo publique (domaine, provider, DNS, coût) reste un runbook
> opérationnel séparé, hors workflow superpowers — non traité ici.

## 1. Contexte et objectif

**Constat.** La roadmap SP-9 demande une « démo publique hébergée (mode
lecture seule) ». Aujourd'hui, aucune notion de « lecture seule globale »
n'existe dans le cœur — seul `canWrite` par collection (SP-4c) et `isAdmin`
(SP-8c) existent, tous deux des permissions *par ressource/utilisateur*, pas
un interrupteur global d'instance.

**Objectif.** Un déploiement démarré avec `CORE_READ_ONLY_MODE=true` refuse
**toute** écriture (REST et MCP, quel que soit l'utilisateur — y compris un
admin), tout en laissant la lecture et l'exploration entièrement
fonctionnelles ; le shell l'affiche clairement (bannière) et masque ses
actions d'écriture en fail-open — même patron que le masquage `canWrite` de
SP-4c, la frontière réelle restant le 403 serveur.

## 2. Périmètre

**Dans le périmètre v1 :**
- `CORE_READ_ONLY_MODE` (bool, défaut `false`) : nouvelle variable d'env
  cœur.
- **REST** : middleware ASGI unique (`app/main.py`) — si
  `CORE_READ_ONLY_MODE` est actif et que la méthode de la requête est
  `POST`/`PUT`/`PATCH`/`DELETE` **et** que le chemin n'est pas `/mcp`
  (traité séparément, cf. ci-dessous), réponse `403` immédiate avant tout
  routing, corps `{"detail": "Mode démo : lecture seule, écritures
  désactivées."}`. Un seul point d'interception plutôt que de modifier
  chacune des ~15 routes de mutation existantes (`items`, `collections`,
  `configs`, `features`, `extensions`, `uploads`, `sharing`) — certaines de
  ces routes (création de collection/extension, upload) ne passent pas par
  `can()` (garde admin-only ou juste l'authentification), donc patcher
  uniquement `can()` ne suffirait pas à tout couvrir ; l'interception par
  verbe HTTP, elle, couvre structurellement tout, y compris les routes
  futures.
- **MCP** : les 4 outils qui écrivent (`save_app_config`, `create_item`,
  `create_form_app`, `set_sharing` — les 6 autres, `whoami`/`list_items`/
  `search_catalog`/`query_features`/`get_item`/`get_app_config`/
  `get_sharing`, restent utilisables) lèvent `ValueError("Mode démo :
  lecture seule, écritures désactivées.")` en tout premier, avant toute
  autre logique — même convention d'erreur que celle déjà en place dans ce
  fichier pour les refus de scope/permission (cf. `_validate_extension_scope`
  et son usage documenté en SP-8c : `ValueError`, pas `HTTPException`,
  transport MCP). Une constante `READ_ONLY_TOOLS = {"save_app_config",
  "create_item", "create_form_app", "set_sharing"}` documente explicitement
  la liste plutôt que de la laisser implicite dans 4 endroits séparés.
- **Nouvel endpoint public `GET /instance`** (aucune authentification requise
  — un visiteur anonyme d'une démo publique doit pouvoir savoir qu'il est en
  lecture seule avant même de se connecter) : `{"readOnly": bool}`. Pas de
  collision de route (`GET /` est déjà pris par la landing page OGC API
  Features).
- **Shell** : hook `useInstanceInfo()` (react-query, fetch `/instance` au
  bootstrap de l'app, dégradation silencieuse à `readOnly: false` en cas
  d'échec réseau — même patron fail-open que `useActiveExtensions` de SP-8b,
  un `/instance` en échec ne doit jamais bloquer le rendu).
  - Bannière persistante dans `AppLayout` si `readOnly === true` : « Mode
    démo — lecture seule, les modifications ne sont pas enregistrées. »
  - Masquage des actions d'écriture déjà identifiées dans le shell —
    réutilise/étend les points de masquage `canWrite` existants (bouton
    Formulaire, écriture Table, `RegisterCollectionDialog`/
    `EditCollectionDialog`/`CollectionShareDialog` de la spec collections,
    `AdminExtensionsPage`) : chacun de ces composants combine sa condition
    existante avec `!readOnly` — pas de nouveau mécanisme de masquage
    générique, extension du patron déjà répété dans ce projet.

**Hors périmètre v1 (explicitement différé) :**
- Hébergement réel (domaine, DNS, provider, coût) — cf. note de périmètre
  en tête de document.
- Réinitialisation périodique automatique des données de démo (cron qui
  reseed/reset la base) — utile pour une vraie démo publique de longue durée
  mais pas nécessaire pour que le mode lecture seule *fonctionne* ; noté
  comme suivi futur, pas un blocage.
- Bandeau/branding spécifique « ceci est une démo » au-delà du message
  lecture seule (page d'accueil dédiée, marketing) — au-delà du « produit
  uniquement » du périmètre décidé.
- Rate limiting différencié pour les visiteurs anonymes de la démo (déjà
  couvert par le rate limiting global de `sp9-securite-minimale`, pas
  dupliqué ici).

## 3. Architecture

### 3.1 Cœur

`app/main.py` : middleware ajouté avant l'inclusion des routers (ordre
important — doit intercepter avant que FastAPI ne résolve la route) :
```python
@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    if (
        settings.CORE_READ_ONLY_MODE
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path != "/mcp"
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Mode démo : lecture seule, écritures désactivées."},
        )
    return await call_next(request)
```
`app/mcp/tools.py` : garde ajoutée en tête de chacun des 4 outils d'écriture
(pas un décorateur générique — 4 lignes identiques, cohérent avec le style
déjà dupliqué de ce fichier plutôt qu'une abstraction pour 4 call sites,
même arbitrage que documenté ailleurs dans ce projet pour `_can_write_
collection`/`_get_writable`).

`app/instance/routes.py` (nouveau module minimal, ou ajouté à un module
existant proche de `auth` — à trancher en tâche) : `GET /instance` public,
lit `settings.CORE_READ_ONLY_MODE` directement, aucune logique
supplémentaire.

### 3.2 Shell

`api/hooks.ts` : `useInstanceInfo()`. `AppLayout` consomme le hook, affiche
la bannière. Chaque composant d'écriture déjà identifié (Formulaire, Table
en mode édition, dialogues admin collections/extensions) reçoit `readOnly`
via le même contexte que celui déjà utilisé pour `useMe()`/`useActiveExtensions`
— pas de prop-drilling manuel, réutilisation du patron de contexte déjà en
place.

## 4. Flux et gestion d'erreurs

**Visiteur anonyme d'une démo en lecture seule :** `GET /instance` (aucune
auth) → `readOnly: true` → bannière visible dès le premier rendu, avant même
toute tentative de connexion.

**Tentative d'écriture malgré le masquage client** (URL forcée, DevTools,
client MCP tiers) : 403 serveur systématique — le masquage client n'est
qu'un confort d'UX, jamais la frontière de sécurité (même principe
explicitement documenté partout ailleurs dans ce projet, ex. SP-4c/SP-8b).

**`/instance` injoignable** (panne réseau transitoire) : le shell suppose
`readOnly: false` par défaut (fail-open sur l'affichage, pas sur la
sécurité — un faux négatif ici expose au pire les boutons d'écriture d'un
visiteur qui recevra un 403 serveur en les utilisant, jamais une vraie
écriture non autorisée).

## 5. Tests

**Core (pytest) :**
- `GET /instance` retourne `readOnly: false` par défaut, `true` si
  `CORE_READ_ONLY_MODE=true` — sans authentification requise.
- Avec `CORE_READ_ONLY_MODE=true` : `POST /items`-équivalent (création de
  config), `PATCH /collections/{id}`, `DELETE /configs/{id}`,
  `PUT /collections/{id}/items/{fid}` (features), `POST /extensions`
  refusent tous en `403`, **y compris pour un utilisateur admin/owner**
  (le mode lecture seule prime sur toute permission normale — testé
  explicitement, pas supposé).
- `GET /items`, `GET /collections/{id}/items`, `GET /me` restent
  fonctionnels en mode lecture seule (la lecture n'est jamais affectée).
- Les 4 outils MCP d'écriture refusent via un vrai handshake `tools/call`
  (pas un appel Python nu — même discipline que SP-8c) ; les 6 outils de
  lecture restent utilisables.

**Shell (Vitest) :**
- `useInstanceInfo` : rendu `readOnly`/dégradation silencieuse sur erreur
  réseau (MSW).
- Bannière visible/absente selon `readOnly`.
- Boutons d'écriture masqués dans Formulaire/Table/dialogues admin quand
  `readOnly === true`, indépendamment de `canWrite`/`isAdmin` (un admin
  avec tous les droits reste masqué en mode démo).

**E2E (nouvelle spec `read-only-demo.spec.ts`) :**
1. `CORE_READ_ONLY_MODE=true` (via mock réseau côté E2E, pas un vrai
   redémarrage de service) : bannière visible, tentative d'action
   d'écriture (Formulaire) : bouton absent/désactivé.
2. Un appel réseau forcé vers une route de mutation (contournant l'UI)
   confirme le 403 serveur — preuve que le masquage n'est pas la seule
   protection.

## 6. Critères d'acceptation

- `CORE_READ_ONLY_MODE=true` bloque toute écriture REST et MCP, pour tout
  utilisateur y compris admin, sans affecter la lecture.
- Un visiteur anonyme voit la bannière lecture seule sans avoir besoin de se
  connecter.
- Toutes les actions d'écriture déjà identifiées dans le shell (Formulaire,
  Table, admin collections, admin extensions) se masquent en fail-open.
- Les 384 tests cœur / 445 tests shell / 34 specs E2E existants restent
  verts ; le nouveau comportement est additif (`CORE_READ_ONLY_MODE=false`
  par défaut, aucun changement observable hors ce mode).
