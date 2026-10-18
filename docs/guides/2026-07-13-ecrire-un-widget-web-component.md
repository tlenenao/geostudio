# Écrire un widget Web Component pour GeoStudio

Un widget GeoStudio peut être écrit sans toucher au dépôt du shell : un
custom element standard (Web Component) + un manifeste JSON, hébergés où
vous voulez, activés par un administrateur de la plateforme depuis
`/admin/extensions`. Cette page prend pour exemple
[`examples/external-widget/`](../../examples/external-widget/), le widget de
référence utilisé par les tests de bout en bout du projet — copiez-le comme
point de départ.

## Le manifeste

```json
{
  "id": "example.external-counter",
  "tag": "external-example-widget",
  "label": "Compteur externe (exemple)",
  "moduleUrl": "https://widgets.example.com/external-counter/widget.js",
  "props": [
    { "name": "initial", "type": "number", "label": "Valeur initiale", "default": 0 }
  ],
  "events": ["changed"],
  "actions": ["reset"],
  "defaultSize": { "w": 2, "h": 2 },
  "permissions": { "collections": "all" },
  "sdkVersion": 1,
  "integrity": "sha384-…",
  "connectHosts": ["https://api.example.org"],
  "imgHosts": ["https://cdn.example.org"]
}
```

> **Préversion (SDK v1).** Le SDK est ouvert en préversion : le contrat DOM ci-dessous est
> versionné (`sdkVersion`), mais il peut encore évoluer entre versions mineures de GeoStudio
> tant que la v1 n'est pas déclarée stable. Un manifeste qui demande une `sdkVersion` que
> l'instance ne connaît pas est refusé (422). Types TypeScript du contrat :
> [`examples/external-widget/sdk.d.ts`](../../examples/external-widget/sdk.d.ts).

- `id` : identifiant unique de votre widget côté tenant (ex. `acme.gauge`) —
  c'est aussi le `widget` référencé dans les configs qui l'utilisent.
- `tag` : le nom du custom element (`customElements.define(tag, …)`).
- `props` : chaque entrée décrit un champ édité dans le panneau de props du
  builder. Quatre types supportés :
  - `string`, `number`, `boolean` : champ simple.
  - `dataSource` : un sélecteur de source de données du builder — la valeur
    transmise à votre widget est l'id d'une `DataSource`, pas directement un
    nom de collection.
- `events` : les noms de `CustomEvent` que votre widget peut émettre ;
  utilisables comme déclencheurs d'actions composées dans le builder.
- `actions` : les noms de méthodes publiques que votre widget expose ;
  utilisables comme cibles d'actions composées.
- `permissions.collections` : `"all"` ou une liste explicite de collections
  — limite les sources de données proposées dans le panneau de props
  (confort d'autorat) **et** est vérifiée côté serveur à l'enregistrement
  d'une config (une config qui route une prop `dataSource` de votre widget
  vers une collection hors de cette liste est rejetée, HTTP 400). Ce n'est
  **pas** une sandbox, voir « Le contrat de confiance ».
- `sdkVersion` : version du contrat DOM (défaut et seule valeur acceptée : `1`).
- `integrity` (facultatif, recommandé) : condensat SRI de votre module
  (`sha256-`, `sha384-` ou `sha512-` + base64). Le navigateur refuse
  d'exécuter un fichier dont le condensat diffère : un fichier remplacé chez
  votre hébergeur ne s'exécute plus. Calcul :
  `openssl dgst -sha384 -binary widget.js | openssl base64 -A`. Le serveur doit
  alors envoyer `Access-Control-Allow-Origin` (le module est chargé en
  `crossorigin="anonymous"`). **Re-calculez-le à chaque publication** : un
  `integrity` périmé rend le widget indisponible.
- `connectHosts` / `imgHosts` (facultatifs) : origines `https://hôte[:port]`
  (sans chemin ni joker) ajoutées à `connect-src` / `img-src` de la CSP de
  l'instance pour les extensions **activées**. Sans déclaration, la CSP
  bloque vos `fetch` et vos images vers un autre domaine ; l'origine du
  module, elle, n'est autorisée que pour le script.

## Le contrat DOM

GeoStudio monte votre élément puis lui assigne, comme **propriétés DOM**
(jamais comme attributs sérialisés en chaîne) :

- `props` : l'objet de props tel que configuré dans le builder.
- `data` : l'état de la source de données référencée par `props.dataSourceId`
  (`{ loading, error, records, … }`) ; `undefined` sans source. Ce n'est
  **pas** le contexte de l'app.
- `user` : l'utilisateur courant (`{ name }`).
- `navigate` : une fonction de navigation entre pages de l'app.
- `variables` (v1) : les variables d'app courantes (`{ nom: valeur }`), en lecture.
- `theme` (v1) : le thème de l'app ; `mode` (v1) : `"edit"`, `"preview"` ou
  `"runtime"` ; `breakpoint` (v1) : `"sm"`, `"md"`… ; `sdkVersion` (v1) : `1`.

Deux méthodes d'écriture (v1) sont aussi posées sur l'élément :

- `setVariable(name, value)` : écrit une variable d'app **existante** (un nom
  inconnu est ignoré, avec un avertissement console).
- `setFilter(sourceId, query)` : pose le filtre d'une source de données de
  l'app (déclenche le recalcul des widgets liés).

Les deux sont **inertes en mode `edit`** (le builder n'est pas un runtime).

L'événement `gs:ready` (`CustomEvent`, `detail.sdkVersion`) est émis une seule
fois sur votre élément quand toutes ces propriétés sont posées ; écoutez-le
dans `connectedCallback` si votre rendu dépend d'elles.

```js
set props(value) {
  this._props = value || {};
  // ré-affiche votre widget avec les nouvelles props
  this._render();
}
```

Pour émettre un événement déclaré dans `events` :

```js
this.dispatchEvent(new CustomEvent("changed", { detail: { count: this._count } }));
```

Pour exposer une action déclarée dans `actions`, définissez simplement une
méthode publique du même nom sur votre élément — GeoStudio l'invoque
directement quand un message composé la cible :

```js
reset() {
  this._count = Number(this._props?.initial ?? 0);
  this._render();
}
```

## Le thème

GeoStudio pose des variables CSS `--gs-*` (couleurs, police…) sur un
ancêtre de votre widget. Elles s'héritent à travers un shadow DOM (les
propriétés personnalisées traversent la frontière) ; un fond explicite reste à
votre charge. Consommez-les directement, rien à initialiser :

```js
span.style.color = "var(--gs-color-text, #0f172a)";
```

## Hébergement et CORS

Sans `integrity`, votre module JS est chargé par un `import()` dynamique **cross-origin**
(avec `integrity` : balise `<script type="module" crossorigin>`, mêmes règles CORS)
(votre domaine, pas celui du shell). Le navigateur applique les règles CORS
à ce chargement : votre serveur doit répondre avec un en-tête
`Access-Control-Allow-Origin` qui autorise l'origine du shell (`*` convient
pour un widget public). Sans cet en-tête, le chargement échoue silencieusement
et GeoStudio affiche un placeholder « Extension indisponible ».

## Le contrat de confiance

Il n'y a **pas de sandbox** en v1 : une extension activée s'exécute avec les
mêmes droits que le reste de la page, donc avec la session de l'utilisateur
(elle peut appeler l'API du cœur en son nom). C'est un compromis assumé
(ADR 0013, `SECURITY.md`) : l'admin qui active votre widget vous fait confiance,
exactement comme pour un widget interne.

`permissions.collections` est **un garde-fou de configuration, pas une
frontière de sécurité** : il empêche d'*enregistrer* une config qui route vers
votre widget une source hors de la liste (props `dataSource` déclarées **et**
`dataSourceId`, widgets imbriqués compris, source `datasetId` jugée sur la
collection du dataset ; une valeur liée par expression est refusée). Votre
code reste libre de faire ses propres requêtes réseau, dans la limite de ce
que le jeton de l'utilisateur autorise déjà côté cœur (RLS/`can()`, inchangés
par les extensions) et de la CSP (`connectHosts`). Seules l'intégrité
(`integrity`) et la confiance accordée à l'hébergeur protègent contre un code
substitué.

## Activation

> Tester en local : le cœur n'accepte qu'une `moduleUrl` HTTPS. Servez
> `widget.js` derrière un certificat de confiance (mkcert, tunnel HTTPS) ou
> enregistrez-le sur une instance de test publiée ; le module doit aussi
> autoriser l'origine du shell (CORS) puisqu'il est chargé par `import()`.

Un administrateur enregistre votre extension depuis `/admin/extensions`
(« Importer un manifeste (JSON) » : collez le manifeste complet ; le bouton
« Modifier » d'une extension existante rouvre le même éditeur) ou via l'API du
cœur (`POST /v1/extensions`, `PATCH /v1/extensions/{id}`, payload = votre manifeste ; `moduleUrl` absolue en
**`https://`** obligatoirement — le cœur refuse toute autre URL en 422) puis
l'active/désactive depuis `/admin/extensions` dans le shell. Les extensions
s'affichent aussi sur les surfaces publiques (`/embed/:token`, `/sites/:slug`,
`/public/items/:pk`), dans le catalogue de l'instance par défaut. Une extension
désactivée disparaît de la palette et affiche un placeholder propre dans les
apps qui l'utilisaient déjà — pas de crash, pas de redéploiement du shell.
