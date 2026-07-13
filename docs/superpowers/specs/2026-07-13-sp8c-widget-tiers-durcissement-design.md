# SP-8c — Widget tiers réel, admin, permissions serveur, containment : design

**Date** : 2026-07-13
**Statut** : validé (brainstorm), prêt pour plan d'implémentation

## Contexte

SP-8a (clos, PR #27) a livré le contrat de widget Web Component et le pont
`WidgetHost` React ↔ custom element. SP-8b (clos, mergé sur `dev` en
b433d94) a livré le chargement dynamique de modules ES par URL et le
registre d'extensions côté cœur (`app.extensions`), activable par un admin
via l'API brute — mais a explicitement reporté cinq chantiers à SP-8c (cf.
spec SP-8b, §Hors périmètre) :

1. Un widget WC développé et hébergé par un **vrai tiers hors de ce repo** —
   l'E2E de SP-8b sert sa fixture en *same-origin* depuis
   `shell/public/fixtures/`, ce qui ne prouve jamais un chargement dynamique
   réellement cross-origin (CORS).
2. UI d'administration dans le shell pour activer/désactiver une extension —
   SP-8b reste API cœur uniquement (comme `app.collections` depuis SP-3a).
3. Validation du scope de permissions **côté cœur** à l'enregistrement d'une
   config — SP-8b ne filtre que côté panneau shell (autorat, pas une
   frontière de sécurité).
4. Containment des erreurs runtime **après montage réussi** d'une extension
   (ex. une méthode d'action qui lève) — limite héritée de SP-8a.
5. Guide « écrire un widget » pour un auteur externe.

SP-8c clôt SP-8 et le jalon **M5 « SDK ouvrable »** de la feuille de route
(`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-8) : « Un widget
écrit par quelqu'un d'autre (ou un agent) sans lire le code du shell ».

État vérifié du code actuel (2026-07-13, après merge SP-8b sur `dev`,
369 tests cœur / 435 tests shell / 30 specs E2E) :

- `shell/src/builder/wc/WcHost.tsx` : monte le custom element, assigne
  `props`/`data`/`user`/`navigate`, relaie les `CustomEvent` vers
  `ActionBus.emit`, invoque les méthodes publiques pour les actions du bus.
  Inchangé par SP-8b, réutilisé par composition par `LazyWcHost`.
- `shell/src/builder/extensions/` (SP-8b) : `LazyWcHost.tsx`,
  `moduleCache.ts` (`ensureModuleLoaded`, mémoïsé par URL, y compris les
  rejets), `registerExtensionWidget.ts`.
- `shell/src/builder/ActionBus.ts` : `emit()` itère synchrone sur les
  messages câblés, **aucun try/catch** autour de l'invocation d'un handler
  (`this.actions.get(...)?.(payload)`) — une exception dans un handler casse
  la boucle et empêche les messages composés suivants de s'exécuter, pour
  *tout* widget (pas spécifique aux extensions, mais c'est le point d'entrée
  par lequel une extension défaillante propage son erreur).
- `shell/src/builder/expr.ts` (`evaluateExpression`) : patron « ne jamais
  lever, logguer et continuer » déjà établi (SP-5a/5b) — modèle repris pour
  le containment.
- `core/app/extensions/` (SP-8b) : `models.py`/`repository.py`/`routes.py`/
  `schemas.py` — table `app.extensions` (clé composite `tenant_id`+`id`),
  `POST`/`PATCH /extensions` admin-only audités, `GET /extensions` retourne
  seulement `enabled=true`, accessible anonyme (tenant par défaut).
- `core/app/auth/routes.py` : `GET /me` (`MeResponse`) retourne
  `id`/`tenantId`/`username`/`email`/`firstName`/`lastName` — **n'inclut pas
  `isAdmin`**. Seul `GET /users` (déjà admin-only) expose `isAdmin` par
  utilisateur — un utilisateur ne peut donc pas savoir s'il est admin sans
  déjà l'être. `is_admin` existe en base (`User.is_admin`, SP-3a).
- `shell/src/api/types.ts` (`Me`) : `{ username, firstName, lastName }` —
  pas de champ admin.
- `shell/src/shell/routes.tsx`/`AppLayout.tsx` : aucune page admin
  n'existe dans le shell aujourd'hui — SP-8c introduit la première.
- `core/app/configs/schemas.py` (`BuilderConfig`) : `layout: Layout | None`
  (top-level, dashboards/maps) + `pages: list[Page]` (apps, chaque page a
  son propre `layout`) ; `LayoutItem.widget: str` (type du widget) +
  `props: dict` (non typé) ; `dataSources: list[DataSource]` avec
  `DataSource.layer` (nom de collection réel).
- `shell/src/builder/wc/generatedPropsPanel.tsx` (`permittedDataSources`,
  SP-8b) : filtre d'autorat qui exclut les `DataSource` dont `.layer`
  n'est pas dans `manifest.permissions.collections` — **pas une frontière
  de sécurité**, commentaire déjà en place dans le code. Un prop
  `dataSource` stocke l'`id` d'un `DataSource` de `config.dataSources`
  (jamais le nom de collection directement).
- `core/app/configs/routes.py` : `create_config`/`update_config`/
  `update_config_by_item`/`rollback_config` — seuls les trois premiers
  reçoivent un `BuilderConfig` neuf du client ; `rollback_config` restaure
  une révision déjà persistée.
- `shell/playwright.config.ts` : un seul `webServer` (`vite preview`, port
  4173) aujourd'hui — Playwright accepte un tableau de `webServer`.

## Objectif

Un widget Web Component écrit **sans lire ce repo**, hébergé sur une
origine distincte, devient utilisable dans le builder après activation par
un admin **depuis le shell** (plus l'API brute) ; une extension qui route
une collection hors de son scope déclaré est rejetée par le cœur, pas
seulement filtrée côté panneau ; une extension dont une action lève une
exception ne casse pas les actions composées des autres widgets ; un guide
documente comment l'écrire.

## Hors périmètre

- Sandbox dure (iframe, ShadowRealm, Web Worker) — arbitrage de la feuille
  de route (A10), non re-débattu.
- Formulaire de création/édition d'extension dans le shell — reste API cœur
  uniquement (payload riche : props/events/actions/permissions), comme
  l'enregistrement de collections depuis SP-3a. Seule l'activation/
  désactivation (geste courant) entre dans le shell.
- Revalidation du scope de permissions au `rollback_config` — restaure une
  révision déjà validée au moment de sa création ; un scope qui se
  resserrerait entre-temps est un cas marginal, non traité ici.
- Containment d'une erreur **interne** à une extension qui ne transite
  jamais par `ActionBus` (son propre listener DOM, un callback async non lié
  à une action déclarée) — JS isole déjà nativement une exception par
  listener (ne plante ni l'onglet ni React), donc pas de nouveau risque
  introduit par les extensions ; même posture que la limite déjà documentée
  de `WidgetErrorBoundary` depuis SP-8a.
- Un vrai hébergement public sur internet (jsdelivr, GitHub Pages) pour
  l'E2E — flaky en CI, contraire à la philosophie déterministe du dépôt
  (`FakeProvider`, fixtures locales). L'E2E utilise un serveur statique
  local dédié sur un port distinct, ce qui suffit à prouver un vrai
  cross-origin (CORS) sans dépendance réseau.
- Opt-in par app, versionnage semver du manifeste — inchangé depuis SP-8b
  (YAGNI confirmé, aucun besoin nouveau identifié).

## Architecture

### 1. Widget tiers réel + guide

Nouveau dossier `examples/external-widget/` à la racine du repo — **hors de
`shell/src`**, jamais importé par le code shell (un vrai tiers ne lit jamais
notre code). Un widget minimal, zéro dépendance de build : JS natif,
`customElements.define(...)` en effet de bord, pas de Lit ni de TypeScript
compilé, pour qu'un auteur externe puisse le copier sans notre toolchain.
Un manifeste JSON à côté (`manifest.json`), conforme à `WcWidgetManifest`.
C'est le matériau concret à la fois de l'E2E et du guide.

**Serveur E2E dédié** : script Node natif (`http.createServer`, aucune
dépendance npm supplémentaire) servant `examples/external-widget/` avec
l'en-tête `Access-Control-Allow-Origin: *`, sur un port distinct (`4174`)
de celui du shell (`4173`). `shell/playwright.config.ts` gagne un second
`webServer` dans le tableau. Le manifeste enregistré via l'API cœur pointe
son `moduleUrl` vers `http://localhost:4174/widget.js` — origine différente
du shell, donc un `import()` réellement soumis aux règles CORS du
navigateur (un widget mal configuré sans le bon en-tête échoue en pratique
de la même façon qu'un vrai déploiement tiers mal configuré).

**Guide** (`docs/guides/2026-07-13-ecrire-un-widget-web-component.md`) :
basé sur `examples/external-widget/`. Couvre : structure du manifeste (4
types de props `string`/`number`/`boolean`/`dataSource`, `events`/
`actions`/`defaultSize`/`permissions`), contrat DOM (`props`/`data`/`user`/
`navigate` assignés comme propriétés, jamais comme attributs sérialisés),
thème hérité via les variables CSS `--gs-*` (rien à faire côté widget, juste
les consommer), CORS requis pour l'hébergement du module, contrat de
confiance (« extension *trusted*, pas de sandbox — l'admin qui active est
responsable »).

### 2. UI d'admin extensions (liste + activer/désactiver)

**Cœur** — `MeResponse` (`core/app/auth/routes.py`) gagne `isAdmin: bool`
(`user.is_admin`, déjà en base, champ trivial). `GET /extensions` gagne un
paramètre `all: bool = False` : si `True` **et** l'appelant est admin,
retourne aussi les extensions `enabled=False` de son tenant ; sinon
comportement inchangé (`enabled=True` uniquement, y compris pour un admin
qui ne passe pas `all=True` — pas de régression du comportement anonyme/
non-admin déjà couvert par les tests SP-8b).

**Shell** — `Me` (`types.ts`) gagne `isAdmin: boolean`, lu par `getMe()`.
Nouvelle route `/admin/extensions` dans `shell/src/shell/routes.tsx`,
protégée par `RequireAuth` (comme les autres) **plus** une garde `isAdmin` :
si faux, message « accès réservé aux administrateurs » (la vraie frontière
reste le 403 serveur sur `PATCH /extensions/{id}`, même patron fail-open
que le Formulaire depuis SP-4c — masquer l'UI n'est jamais la sécurité).
Lien « Administration » dans `AppLayout`, visible seulement si `isAdmin`.
`AdminExtensionsPage` : liste (tag, label, moduleUrl, enabled) via
`GET /extensions?all=true`, toggle par ligne (`PATCH /extensions/{id}` avec
`enabled`). Pas de formulaire de création — l'enregistrement initial reste
API cœur uniquement (cf. Hors périmètre).

### 3. Validation des permissions côté cœur

Nouvelle fonction `validate_extension_permissions(session, config,
tenant_id)` (`core/app/configs/` — module à trancher en écrivant le plan,
probablement `core/app/configs/extension_validation.py` pour ne pas
alourdir `routes.py`), appelée dans `create_config`/`update_config`/
`update_config_by_item`, après le parsing Pydantic structurel de
`BuilderConfig`, avant l'écriture :

1. Rassemble tous les `LayoutItem` du config (`config.layout.items` si
   présent + `page.layout.items` pour chaque page).
2. Résout par lot les `item.widget` qui correspondent à un `id` d'extension
   enregistrée pour ce tenant (`WHERE tenant_id=… AND id IN (…)`, **toutes**
   les extensions du tenant, activées ou non — un widget qui ne matche
   aucune extension, càd un widget interne, est ignoré, aucun changement de
   comportement pour eux).
3. Pour chaque prop de type `dataSource` déclarée par `extension.props` et
   renseignée dans `item.props`, résout l'id vers `config.dataSources[].layer`
   (miroir Python du filtre shell `permittedDataSources`, même duplication
   assumée que `form_fields_from_schema`/CEL-A8).
4. Vérifie ce `layer` contre `extension.permissions.collections` (`"all"`
   ou liste explicite) — sinon **400** avec un message explicite
   (identifiant du widget, nom de la prop, collection refusée).

### 4. Containment des erreurs runtime post-montage

`ActionBus.emit()` (`shell/src/builder/ActionBus.ts`) : wrap l'invocation
de chaque handler dans un try/catch, `console.error` et `continue` — même
patron « ne jamais lever, logguer et continuer » que `evaluateExpression`
(SP-5a/5b). Corrige le cas général (tout widget) en même temps que le cas
extension, sans code spécifique dans `WcHost`/`LazyWcHost`.

```ts
for (const m of list) {
  if (m.when && !evaluateExpression(m.when, { ...this.context, record })) continue;
  try {
    this.actions.get(`${m.to} ${m.action}`)?.(payload);
  } catch (err) {
    console.error(`Action bus: handler for "${m.to} ${m.action}" threw`, err);
  }
}
```

## Tests

**Cœur (pytest)** :
- `MeResponse` inclut `isAdmin` (reflète `user.is_admin`).
- `GET /extensions?all=true` : admin voit aussi les `enabled=false` de son
  tenant ; non-admin/anonyme continue de ne voir que `enabled=true` même
  avec `all=true` ; test adversarial tenant A / tenant B (patron SP-8b).
- `validate_extension_permissions` : config avec un widget d'extension +
  prop `dataSource` hors scope → 400 ; dans le scope explicite ou `"all"` →
  200 ; widget non-extension → jamais affecté ; sur `create_config` et
  `update_config` ; `rollback_config` non affecté (test de non-régression).

**Shell (Vitest)** :
- `Me`/`getMe` porte `isAdmin`.
- `AdminExtensionsPage` : liste rendue depuis `GET /extensions?all=true`,
  toggle appelle `PATCH` avec le bon `enabled`, page affiche le message
  d'accès refusé si `isAdmin=false` (sans appeler l'API).
- `ActionBus.emit` : un handler qui lève n'empêche pas les handlers
  suivants du même `emit()` de s'exécuter (test dédié, régression du bug
  latent démontrée par un handler mocké qui lève).

**E2E (Playwright)** :
- `external-widget.spec.ts` — le widget de `examples/external-widget/`
  servi cross-origin (port 4174, CORS), manifeste enregistré via l'API
  cœur, activé, apparaît dans la palette, se pose sur le canvas, se
  comporte comme un widget WC ordinaire (props par défaut, thème, event →
  action composée, action du bus → méthode publique — mêmes vérifications
  que `wc-widget-bridge.spec.ts`/`extension-widget.spec.ts`).
- Un test admin : connecté en admin, `/admin/extensions` liste l'extension
  et la désactive en direct (toggle → `PATCH` → disparaît de la liste des
  actives).
- Un test non-admin : `/admin/extensions` affiche le message d'accès
  refusé, aucun appel `PATCH` possible depuis l'UI.
- Un test containment : un widget d'extension dont l'action lève une
  exception ne bloque pas un message composé suivant dans la même chaîne,
  vers un autre widget (assertion sur l'effet du second widget).
- Les 30 specs E2E existantes restent vertes.

## Critères d'acceptation (clôture SP-8, jalon M5)

- Un widget WC écrit sans lire ce repo, hébergé sur une origine distincte
  du shell, s'active et fonctionne dans le builder (palette, canvas, thème,
  events, actions composées) sans redéploiement du shell.
- Un admin peut voir et activer/désactiver une extension depuis une page du
  shell, sans passer par l'API brute.
- Une config qui route une collection hors du scope déclaré d'une extension
  est rejetée par le cœur (400), pas seulement filtrée côté panneau.
- Une extension dont une action lève une exception ne casse pas les actions
  composées d'autres widgets dans la même chaîne.
- Guide « écrire un widget » publié, basé sur l'exemple réel utilisé par
  l'E2E.
- Aucune régression sur le `Compteur` WC (SP-8a), les extensions SP-8b, ni
  les 30 specs E2E existantes.
