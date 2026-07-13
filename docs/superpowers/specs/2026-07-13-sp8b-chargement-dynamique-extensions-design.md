# SP-8b — Chargement dynamique de modules ES + registre d'extensions : design

**Date** : 2026-07-13
**Statut** : validé (brainstorm), prêt pour plan d'implémentation

## Contexte

SP-8a (clos, PR #27) a livré le contrat de widget Web Component et le pont
`WidgetHost` React ↔ custom element, validé sur le `Compteur` porté en Lit —
mais ce widget est statiquement bundlé dans le repo shell
(`registerCounterWcExampleWidget()` appelé au chargement du module). SP-8b
ajoute ce qui manque pour qu'un widget WC puisse être écrit et servi **hors du
repo shell** : chargement dynamique d'un module ES par URL, registre
d'extensions côté cœur activable par l'admin, un mécanisme de permissions
déclaratives, et une robustesse minimale face à une extension qui ne charge
pas ou est désactivée.

Comme SP-4/SP-6/SP-7/SP-8a, ce découpage suit la feuille de route
(`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-8) :

- **SP-8a (clos)** : le contrat WC + le pont, prototypé sur le `Compteur`.
- **SP-8b (cette spec)** : chargement dynamique + registre d'extensions +
  permissions déclaratives + robustesse de base.
- **SP-8c** : guide « écrire un widget », durcissement, E2E de bout en bout
  avec un vrai widget développé hors repo par un tiers.

Arbitrage de la feuille de route repris tel quel : **pas de sandbox dure en
v1** — extensions *trusted*, permissions déclaratives, compromis assumé
(vision §5, A10).

État vérifié du code actuel (2026-07-13, après merge de SP-8a) :

- `shell/src/builder/wc/manifest.ts` : `WcWidgetManifest` (`type`, `tag`,
  `label`, `props[]` typées `string|number|boolean`, `events?`, `actions?`,
  `defaultSize`).
- `shell/src/builder/wc/registerWcWidget.ts` : construit un `WidgetDefinition`
  standard depuis un manifeste et l'enregistre via `registerWidget`
  (`registry.ts`, inchangé depuis SP-8a).
- `shell/src/builder/wc/WcHost.tsx` : monte le custom element, assigne
  `props`/`data`/`user`/`navigate` comme propriétés DOM, relaie les
  `CustomEvent` vers `ActionBus.emit`, invoque les méthodes publiques pour les
  actions du bus. Ne fait aucune hypothèse sur l'origine du module qui a
  défini le tag — **inchangé par SP-8b**, réutilisé par composition.
- `shell/src/builder/wc/generatedPropsPanel.tsx` : un champ par entrée de
  `manifest.props`, texte/nombre/case à cocher.
- `shell/src/builder/DataSourceSelect.tsx` : `<select>` de `DataSource[]`
  (existant, utilisé par les widgets React `chart`/`mapWidget`/`form`/
  `indicator`/`data` via leur propre `PropsPanel`) — **réutilisé tel quel**
  pour le nouveau type de prop `dataSource`.
- `shell/src/api/types.ts` (`ItemClient`) : interface unique par laquelle le
  shell parle au cœur (règle d'architecture n°1 du CLAUDE.md) ; `itemClient.ts`
  a déjà un précédent direct pour un objet non-catalogue scopé tenant :
  `fetchCoreCollections` (`GET /collections`), appelé par
  `listLayerSources`.
- `core/app/collections/` : précédent direct pour un registre admin non-item
  — table dédiée (`app.collections`, pas `app.items`), `_require_admin`,
  scoping tenant systématique (`user.tenant_id`), `write_audit` sur chaque
  écriture, `list_visible_collections` accessible anonyme (résout un tenant
  par défaut). **`app.extensions` suit exactement ce patron.**
- `shell/e2e/mocks.ts` : intercepte le réseau par `page.route`, pas de faux
  `ItemClient` — les futurs tests E2E interceptent `**/extensions*` de la
  même façon que `**/collections*` aujourd'hui.

## Objectif

Un widget Web Component écrit et hébergé **hors du repo shell** (manifeste +
module ES servis par une URL) devient disponible dans le builder après
activation par un admin, sans redéploiement du shell : palette, canvas,
thème, events, actions composées — exactement comme un widget interne ou
comme le `Compteur` WC de SP-8a. Sa désactivation ne casse pas les apps qui
l'utilisaient.

## Hors périmètre (reporté à SP-8c, ou non retenu après clarification)

- Un vrai widget développé par un tiers réel hors de ce repo — l'E2E de
  SP-8b utilise une fixture JS locale servie en same-origin (voir §Tests) ;
  le scénario "développeur externe, guide, widget non lu par nous" est
  l'E2E de clôture de SP-8c.
- UI d'administration dans le shell pour enregistrer/activer une extension —
  API cœur uniquement en SP-8b (même situation que l'enregistrement de
  collections aujourd'hui, aucune UI shell).
- Validation du scope de permissions **côté cœur** à l'enregistrement d'une
  config — SP-8b l'applique uniquement côté shell (le panneau de props ne
  propose/n'accepte que les collections déclarées) ; la vraie frontière de
  sécurité sur les données reste inchangée (RLS/`can()` déjà en place sur OGC
  API Features). Un rejet serveur d'une config qui violerait le scope
  déclaré est un chantier à part, plus approprié au durcissement SP-8c.
- Validation/blocage d'un numéro de version semver du manifeste — YAGNI ;
  un champ `version` informatif n'est même pas ajouté (aucun besoin
  identifié tant qu'il n'y a pas de marketplace).
- Containment des erreurs runtime **après** montage réussi d'une extension
  (ex. exception dans un de ses propres listeners) — limite documentée
  héritée de SP-8a (`WidgetErrorBoundary` ne capture que les erreurs
  synchrones de rendu React), non traitée ici.
- Opt-in par app ("cette app utilise les extensions X, Y") — une extension
  activée par l'admin est visible dans la palette de toutes les apps du
  tenant, comme les widgets internes aujourd'hui.
- Sandbox dure (iframe, ShadowRealm, Web Worker) — arbitrage de la feuille de
  route, non re-débattu ici.
- Retrait du chemin d'enregistrement statique de SP-8a (`registerWcWidget`,
  `Compteur` WC bundlé) — les deux mécanismes coexistent : un widget WC
  interne au repo reste statiquement enregistré, un widget d'extension passe
  par le nouveau chemin dynamique.

## Architecture

### Modèle de données côté cœur

Nouvelle table `app.extensions` (même famille que `app.collections`,
SP-3a) :

| Colonne | Type | Note |
|---|---|---|
| `id` | text | = `type` du widget (ex. `"acme.gauge"`) ; **pas unique seul** — deux tenants peuvent enregistrer le même `type` |
| `tenant_id` | text, FK tenants | scoping systématique, comme partout ailleurs |
| `owner_id` | FK users | admin qui a enregistré l'extension |
| `tag` | text | nom de l'élément custom (ex. `"acme-gauge"`) |
| `label` | text | libellé palette |
| `module_url` | text | URL https du module ES ; aucune validation de contenu, l'admin est responsable de ce qu'il enregistre |
| `props` | jsonb | `WcWidgetManifest["props"]` |
| `events` | jsonb, nullable | `string[]` |
| `actions` | jsonb, nullable | `string[]` |
| `default_size` | jsonb | `{ w, h }` |
| `permissions` | jsonb | `{ "collections": string[] \| "all" }` |
| `enabled` | boolean | défaut `true` à la création |
| `created_at` | timestamptz | |

Clé primaire composite `(tenant_id, id)` — même principe qu'une contrainte
d'unicité par tenant, sans surrogate séparé (contrairement à
`Collection.id`/`table_name`, il n'y a ici aucune ressource physique sous-
jacente distincte à découpler du nom d'enregistrement). Endpoints
(`core/app/extensions/`, nouveau module) :

- `POST /extensions` — admin uniquement (`_require_admin`, même garde que
  `register_collection`) ; 409 si `id` (= `type`) déjà pris pour ce tenant ;
  audit `extension.create`.
- `PATCH /extensions/{id}` — admin uniquement ; met à jour un sous-ensemble
  de champs (notamment `enabled` — c'est le mécanisme d'activation/
  désactivation) ; audit `extension.update`.
- `GET /extensions` — retourne les extensions `enabled=true` du tenant
  appelant ; accessible anonyme comme `list_visible_collections` (résout un
  tenant par défaut si pas d'utilisateur), pour qu'une app publiée utilisant
  une extension se rende aussi pour un visiteur anonyme.

Pas de `DELETE` (YAGNI — `PATCH enabled=false` suffit pour désactiver).

### Manifeste et types (shell)

`WcWidgetManifest` (`shell/src/builder/wc/manifest.ts`, SP-8a) gagne deux
champs optionnels, rétrocompatibles avec tout manifeste existant (le
`Compteur` WC n'en a besoin d'aucun) :

```ts
export type WcWidgetManifest = {
  // ... champs SP-8a inchangés ...
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean" | "dataSource"; // + "dataSource"
    label: string;
    default: unknown;
  }>;
  permissions?: { collections: string[] | "all" }; // nouveau, optionnel
};
```

Nouveau module `shell/src/builder/extensions/` (à côté de `wc/`, mêmes
contraintes que SP-8a : **aucune modification de `registry.ts`,
`WidgetHost.tsx`, `PropsPanel.tsx`, `ActionsPanel.tsx`, `WidgetPalette.tsx`**) :

```ts
// extensions/manifest.ts
export type ExtensionManifest = WcWidgetManifest & { moduleUrl: string };
```

### `ItemClient` — nouvelle méthode de lecture

Règle d'architecture n°1 (CLAUDE.md) : le shell ne parle au cœur qu'à travers
`ItemClient`. Nouvelle méthode sur l'interface (`shell/src/api/types.ts`) :

```ts
listActiveExtensions(): Promise<ExtensionManifest[]>;
```

Implémentée dans `itemClient.ts` au même endroit que `fetchCoreCollections`
(`fetch(`${coreUrl}/extensions`)`, en-tête `Authorization` si connecté).
Seule méthode ajoutée à l'interface — l'enregistrement/activation admin
(`POST`/`PATCH /extensions`) ne passe par aucun chemin shell (API cœur
uniquement, cf. hors périmètre).

### Chargement : bootstrap éager des manifestes, import paresseux du code

`extensions/loadExtensions.ts` :

```ts
export async function loadActiveExtensions(client: ItemClient): Promise<void> {
  const manifests = await client.listActiveExtensions();
  for (const manifest of manifests) {
    registerExtensionWidget(manifest); // n'importe rien encore
  }
}
```

Appelé par un effet async dans `AppBuilderPage.tsx`/`AppRuntimePage.tsx`
(déjà modifiés en SP-8a pour enregistrer le `Compteur` WC) avant le premier
rendu du builder/runtime (état de chargement minimal le temps du fetch —
un aller-retour JSON, coût négligeable). Un manifeste individuellement
invalide (ex. `props` malformé) est ignoré (log console), n'empêche pas
l'enregistrement des autres.

`registerExtensionWidget(manifest)` (`extensions/registerExtensionWidget.ts`)
construit un `WidgetDefinition` comme `registerWcWidget` (réutilise
`makeGeneratedPropsPanel`), avec `Component: makeLazyWcHost(manifest)`.

`makeLazyWcHost(manifest)` (`extensions/LazyWcHost.tsx`) :

```tsx
export function makeLazyWcHost(manifest: ExtensionManifest) {
  const WcHost = makeWcHost(manifest); // SP-8a, réutilisé tel quel

  return function LazyWcHost(p: { props: Record<string, unknown>; ctx: WidgetContext }) {
    const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
    useEffect(() => {
      let cancelled = false;
      ensureModuleLoaded(manifest.moduleUrl)
        .then(() => !cancelled && setStatus("ready"))
        .catch(() => !cancelled && setStatus("error"));
      return () => { cancelled = true; };
    }, []);

    if (status === "loading") return <Placeholder text="Chargement…" />;
    if (status === "error") return <Placeholder text="Extension indisponible" />;
    return <WcHost {...p} />;
  };
}
```

`ensureModuleLoaded(url)` (`extensions/moduleCache.ts`) : `Map<string,
Promise<unknown>>` module-level, clé = `moduleUrl` — deux instances du même
type d'extension ne réimportent pas le module deux fois ; la promesse
rejetée est aussi mise en cache (un import cassé ne réessaie pas à chaque
montage, cohérent avec « pas de retry » — un admin corrige via `PATCH`).

Le module lui-même s'auto-enregistre (`customElements.define(...)`) au
premier `import()`, exactement comme `gs-counter` (SP-8a) — aucun export
particulier requis, la seule obligation pour l'auteur d'extension est
d'appeler `customElements.define(tag, ...)` en effet de bord du module.

### Prop `dataSource` et permissions

`makeGeneratedPropsPanel` (SP-8a, étendu) gagne un cas pour
`type: "dataSource"` : rend un `<DataSourceSelect>` au lieu d'un `<input>`.
`dataSources` (déjà passé par `PropsPanel.tsx`, signature inchangée) est
filtré selon `manifest.permissions` :

- absent → tout `dataSources` proposé (widgets sans permissions déclarées,
  y compris tout `WcWidgetManifest` de SP-8a).
- `{ collections: "all" }` → tout proposé.
- `{ collections: string[] }` → seules les `DataSource` dont `.layer` figure
  dans la liste sont proposées/acceptées.

C'est une frontière **UX/gouvernance**, pas une frontière de sécurité — la
vraie autorisation sur les données reste RLS/`can()` sur OGC API Features,
inchangés. Une extension qui ignorerait cette convention et ferait ses
propres requêtes réseau ne serait pas bloquée : compromis assumé (« pas de
sandbox dure en v1 »), cohérent avec le hors-périmètre ci-dessus.

### Robustesse

- **Extension désactivée** (`enabled=false`) : absente de
  `listActiveExtensions()` → aucun `WidgetDefinition` enregistré pour son
  `type` → `WidgetHost` (mécanisme générique existant, inchangé) affiche son
  placeholder pour un type de widget inconnu sur toute app qui l'utilisait.
  Pas de redéploiement du shell nécessaire.
- **Import réseau en échec** (404, CORS, timeout) : `makeLazyWcHost` affiche
  un placeholder propre pour ce widget précis, sans propager l'erreur au
  reste de l'app.
- **Erreur runtime après montage réussi** : hors périmètre (cf. plus haut).

## Tests

**Cœur (pytest, `core/tests/extensions/`)** :
- `POST /extensions` : 403 non-admin, 409 sur `id` déjà pris (même tenant),
  succès + audit `extension.create`.
- `PATCH /extensions/{id}` : 403 non-admin, met à jour `enabled` et audite
  `extension.update`.
- `GET /extensions` : ne retourne que `enabled=true` du tenant appelant ;
  test adversarial — une extension du tenant A n'apparaît jamais dans la
  réponse pour un utilisateur du tenant B (même patron que les tests
  adversariaux de SP-7) ; accessible sans authentification (tenant par
  défaut).

**Shell (Vitest, `shell/src/builder/extensions/`)** :
- `listActiveExtensions` (itemClient) : construit l'URL, parse la réponse.
- `registerExtensionWidget` : construit un `WidgetDefinition` correct depuis
  un `ExtensionManifest` (mêmes assertions que `registerWcWidget.test.tsx`
  de SP-8a, plus le passage de `moduleUrl`).
- `makeLazyWcHost` : affiche le placeholder de chargement pendant l'import,
  délègue à `WcHost` (SP-8a) une fois résolu, affiche le placeholder
  d'erreur si l'import échoue (module inexistant/tag jamais défini), le
  cache par URL n'importe qu'une fois pour deux instances du même type.
- `generatedPropsPanel` : le prop `dataSource` rend un `DataSourceSelect`
  filtré par `permissions.collections` (liste explicite, `"all"`, et absence
  de `permissions` → aucun filtrage).

**E2E (Playwright)** : nouvelle spec `extension-widget.spec.ts` — `**/extensions`
mocké renvoie un manifeste dont `moduleUrl` pointe vers une fixture JS servie
en same-origin (`shell/public/fixtures/`, servie telle quelle par le serveur
de preview Playwright) ; le widget apparaît dans la palette sous son
`label`, se pose sur le canvas, se comporte comme un widget WC ordinaire
(props par défaut, thème, event → action composée, action du bus → méthode
publique — mêmes vérifications que `wc-widget-bridge.spec.ts` de SP-8a).
Un second test : le mock `**/extensions` renvoie une liste sans cette
extension (désactivée) sur une app qui l'utilise déjà — vérifie le
placeholder au lieu d'un crash. Les 28 specs E2E existantes restent vertes.

## Critères d'acceptation

- Un widget WC dont le manifeste et le module JS sont servis par une simple
  URL (aucun code dans le repo shell) devient disponible dans la palette dès
  qu'un admin l'active via l'API cœur, sans redéploiement du shell.
- Le widget se pose, reçoit ses props (dont un prop `dataSource` filtré par
  permissions), s'affiche stylé selon le thème courant, émet des events qui
  déclenchent des actions composées, répond aux actions du bus — même
  comportement que le `Compteur` WC de SP-8a.
- Désactiver une extension ne casse pas les apps qui l'utilisaient
  (placeholder propre au lieu d'un crash), sans redéploiement du shell.
- Un import de module en échec (URL invalide/injoignable) affiche un
  placeholder propre limité au(x) widget(s) concerné(s), sans propager
  l'erreur au reste de l'app.
- Aucune régression sur le `Compteur` WC (SP-8a), le `Compteur` React, ni
  les 28 specs E2E existantes.
