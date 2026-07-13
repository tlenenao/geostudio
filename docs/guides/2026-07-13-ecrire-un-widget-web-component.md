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
  "moduleUrl": "widget.js",
  "props": [
    { "name": "initial", "type": "number", "label": "Valeur initiale", "default": 0 }
  ],
  "events": ["changed"],
  "actions": ["reset"],
  "defaultSize": { "w": 2, "h": 2 },
  "permissions": { "collections": "all" }
}
```

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
  vers une collection hors de cette liste est rejetée, HTTP 400).

## Le contrat DOM

GeoStudio monte votre élément puis lui assigne, comme **propriétés DOM**
(jamais comme attributs sérialisés en chaîne) :

- `props` : l'objet de props tel que configuré dans le builder.
- `data` : les données courantes de l'app (variables, contexte).
- `user` : l'utilisateur courant.
- `navigate` : une fonction de navigation.

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
ancêtre de votre widget. Consommez-les directement, rien à initialiser :

```js
span.style.color = "var(--gs-color-text, #0f172a)";
```

## Hébergement et CORS

Votre module JS est chargé par un `import()` dynamique **cross-origin**
(votre domaine, pas celui du shell). Le navigateur applique les règles CORS
à ce chargement : votre serveur doit répondre avec un en-tête
`Access-Control-Allow-Origin` qui autorise l'origine du shell (`*` convient
pour un widget public). Sans cet en-tête, le chargement échoue silencieusement
et GeoStudio affiche un placeholder « Extension indisponible ».

## Le contrat de confiance

Il n'y a **pas de sandbox** en v1 : une extension activée s'exécute avec les
mêmes droits que le reste de la page. C'est un compromis assumé — l'admin
qui active votre widget vous fait confiance, exactement comme il ferait
confiance à un widget interne. `permissions.collections` est un confort
d'autorat et une vraie frontière serveur pour les props `dataSource`
déclarées dans votre manifeste, pas une sandbox : votre code reste libre de
faire ses propres requêtes réseau, dans la limite de ce que le token de
l'utilisateur autorise déjà côté cœur (RLS/`can()`, inchangés par les
extensions).

## Activation

Un administrateur enregistre votre extension via l'API du cœur
(`POST /extensions`, payload = votre manifeste + `moduleUrl` absolue) puis
l'active/désactive depuis `/admin/extensions` dans le shell. Une extension
désactivée disparaît de la palette et affiche un placeholder propre dans les
apps qui l'utilisaient déjà — pas de crash, pas de redéploiement du shell.
