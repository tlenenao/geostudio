# L10 « SDK et extensions » — spec (AUD-107, 108, 109, 110)

Source : `docs/revue/audit-2026-10-16/dimensions/d24.md`, `99-synthese.md` §4 (L10), décision **D5**
(SDK ouvert en **préversion**, contrat DOM versionné, seulement après réparation du rendu public et
de la frontière de permissions). Couloir B, 2e mission. Migration réservée : **0171**.

## Vérification des prémisses (code réel, 2026-10-19)

| AUD | Constat d24 | État constaté |
|---|---|---|
| 107 | Extensions non enregistrées sur `EmbedPage`/`SitePublicPage`/`PublicItemPage`/`DatasetPage` | **Confirmé** : seuls `AppRuntimePage`, `AppBuilderPage` et `staticExport/entry.tsx` enregistrent. `GET /extensions` est déjà anonyme. |
| 108 | `dataSourceId` contourne `permissions.collections` | **Côté cœur déjà corrigé** (`b8df35f0`, `extension_permissions.py` : `dataSourceId` vérifié, sources non résolues/expressions refusées, imbriqués, datasets). Reste : la doc annonce encore « une vraie frontière serveur ». |
| 109 | CSP bloque `connect-src`/`img-src` de l'extension ; aucune intégrité | **Confirmé** (`compute_csp_allowlist` : seuls les hôtes de tuiles ; `import(url)` brut). |
| 110 | Contrat DOM minimal, sans version ; UI d'admin squelette | **Confirmé** (`WcHost` n'assigne que props/data/user/navigate ; `ExtensionCreate` sans `sdkVersion` ; `RegisterForm` à 4 champs, aucun PATCH). Constats mineurs 7/8/9 de d24 repris car ils touchent les mêmes fichiers. |

## Décisions (défauts raisonnables, à valider)

1. **Contrat v1 versionné** : `sdkVersion: int` au manifeste (défaut `1`, seule valeur acceptée : `Literal[1]`,
   un manifeste `2` est refusé en 422 tant que le shell ne le sait pas). Colonne `extensions.sdk_version`.
2. **Surface DOM v1** assignée à l'élément (en plus de `props`/`data`/`user`/`navigate`) :
   `variables` (lecture), `theme`, `mode`, `breakpoint`, `sdkVersion`, et les méthodes
   `setVariable(name, value)` et `setFilter(sourceId, query)`. Événement `gs:ready` (CustomEvent non bulleux
   sur l'élément) émis une fois, après la première assignation. Écritures **inertes en mode `edit`**
   et pour un nom de variable absent de l'app (`console.warn`). `query(datasetId, spec)` du d24 est
   **reporté** (hors préversion : il ouvre une surface `can()` à part).
3. **Pas de paquet npm `@geostudio/widget-sdk`** : types livrés en `examples/external-widget/sdk.d.ts` + guide
   (YAGNI avant ouverture réelle ; décision produit D5 « préversion »).
4. **Intégrité (AUD-109 #4)** : champ `integrity` facultatif (`sha384-<base64>`/`sha256-`/`sha512-`), vérifié par
   le navigateur via `<script type="module" integrity crossorigin>` (compatible `script-src 'self' <origine>` ;
   pas de Blob URL, qui exigerait `blob:` dans `script-src`). Le cache de modules est indexé par
   `url + integrity`. Facultatif = rétrocompatible ; l'UI d'admin affiche un badge « sans intégrité ».
   Pas d'exigence instance-wide (`CORE_…_REQUIRE_INTEGRITY`) dans ce lot.
5. **CSP (AUD-109 #3)** : champs déclaratifs `connectHosts` et `imgHosts` (origines `https://hôte[:port]`,
   sans chemin ni joker), agrégés dans `compute_csp_allowlist` pour les extensions **activées**. Colonnes JSON
   `connect_hosts`, `img_hosts` (0171). Écart assumé vs d24 (« au minimum l'origine du module ») : l'origine
   du module n'est **pas** ajoutée implicitement à `connect-src`/`img-src` — deux tests de non-régression
   existants (`test_security_service.py`) l'interdisent délibérément ; seule la déclaration explicite élargit.
   Pas de `font-src`/`media-src` (absents de la CSP rendue).
6. **Catalogue rafraîchi (d24 #9, #7)** : `unregisterWidget` + hook `useRegisterExtensions()` unique qui
   réconcilie le registre avec la liste active (retire les types disparus, ré-enregistre uniquement un
   manifeste modifié, donc plus de `console.warn` d'écrasement) ; `ensureModuleLoaded` retire une promesse
   rejetée du cache ; après chargement, on attend `customElements.whenDefined(tag)` (3 s) sinon erreur lisible.
7. **UI d'admin (AUD-110 #6)** : formulaire d'enregistrement par **import d'un manifeste JSON** (validé par
   `ExtensionCreate` côté cœur, erreurs 422 affichées) en plus du formulaire minimal, et **édition** d'une
   extension existante par le même éditeur JSON (PATCH). Outils MCP d'enregistrement : **reportés**
   (privilège admin ; pas de besoin d'IA avant l'ouverture). Écosystème signé/marketplace (d24 #10) : hors lot.
8. **AUD-108** : pas de nouveau code côté cœur ; ajout de tests de non-régression sur le chemin shell
   (`WcHost` ne passe `data` que de la source résolue) et **réécriture de la doc** : `permissions.collections`
   est un confort d'autorat/garde de config, **pas** une sandbox (le code tiers a la session).

## Hors périmètre
Sandbox iframe + postMessage, signature cosign, marketplace, `query()` du contrat, outils MCP.

## Surfaces nouvelles (à inventorier par le contrôleur)
Aucune route REST nouvelle (`POST/PATCH/GET /extensions` étendus en entrée/sortie). Route shell : aucune
(l'éditeur vit dans `/admin/extensions`). Une route shell `/admin/copilot` (L9, mission 1) est à inventorier.
