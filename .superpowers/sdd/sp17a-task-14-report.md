# Task 14 report — E2E export depuis la visionneuse de carte

Commit: `0c9c8d9` — `test(e2e): SP-17a — exporter une carte en PDF, capacité désactivée cache le bouton`
File: `shell/e2e/export.spec.ts` (new, 95 lines, 2 tests)

## Ce qui a été implémenté

Deux tests Playwright dans `shell/e2e/export.spec.ts` :

1. **Happy path** : crée une carte via la vraie UI (dialogue "Nouveau" →
   type "map" → titre → "Créer"), atterrit sur `/maps/77` (item id réel du
   fixture `mockCore`, pas l'id `map-1` du skeleton du brief), ouvre
   "Exporter", clique "PDF" dans le dialogue "Choisir le format d'export",
   vérifie le corps exact du `POST /export`, poll `GET /export/jobs/...`
   jusqu'à `"done"`, vérifie le lien de téléchargement avec le `resultUrl`
   exact du mock.
2. **Capacité désactivée** : `exportEnabled: false` sur `/instance` → le
   bouton "Exporter" est absent (`toHaveCount(0)`).

## Vérification des sélecteurs réels (avant d'écrire les assertions)

Lu le code source réel plutôt que de deviner :
- `shell/src/pages/MapEditorPage.tsx` — confirmé que `/maps/:pk`
  (`MapEditorRoute` dans `routes.tsx`) est bien la page qui rend
  `<ExportPanel itemId={pk} />` de façon inconditionnelle sur
  `exportEnabled` (contrairement à `AppRuntimePage`, qui exige en plus
  `interactions === "auto"`) — donc `/maps/map-1` du brief était la bonne
  cible de route, mais l'id "map-1" ne correspond à rien dans le fixture
  partagé `mocks.ts`.
- `shell/src/builder/print/ExportPanel.tsx` — texte exact du bouton
  "Exporter", titre du dialogue "Choisir le format d'export", labels des
  boutons "PNG"/"PDF", texte du lien "Télécharger l'export", et la forme du
  poll (`GET /export/jobs/{jobId}` en boucle tant que `pending`/`running`).
- `shell/src/api/itemClient.ts` (lignes 843-849) — `createExport` poste
  `{ itemId, format }` sur `POST /export`, `getExportJob` sur
  `GET /export/jobs/{jobId}` — confirme le contrat que le mock intercepte.
- `shell/src/ui/dialog.tsx` — `role="dialog"` + `aria-label={title}`,
  confirme que `getByRole("dialog", { name: ... })` fonctionne tel quel.
- `shell/e2e/mocks.ts` — `mockCore()` route déjà `POST /configs` (kind
  "map") vers `itemId: "77"` et sert `DEFAULT_MAP_CONFIG` sur
  `GET /configs/by-item/77` ; a donc adapté le skeleton du brief pour créer
  la carte via l'UI (comme `e2e/map-editor.spec.ts` et
  `e2e/dataset-export.spec.ts` le font déjà) plutôt que de naviguer en dur
  vers un item id inexistant côté fixture.
- `shell/e2e/alert-rule.spec.ts` et `shell/e2e/dataset-export.spec.ts` —
  patron d'assertion profonde sur le corps du POST (`toEqual`/`toMatchObject`
  avec commentaire explicite citant le piège SP-16b), patron de
  `mockCore(page)` + surcharge de route ajoutée après (dernier enregistré
  gagne).

## Résultat des tests

- `npx playwright test e2e/export.spec.ts` : **2/2 PASS**.
- `npm run e2e` (suite complète) : **94/94 PASS**, 0 régression sur les 92
  specs préexistantes (13+ fichiers, dont `alert-rule`, `pipeline-builder`,
  `dataset-export`, `map-editor`, `analytics-context` et tous les autres).

## Auto-revue — profondeur des assertions

- Le corps du `POST /export` est vérifié avec `toEqual({ itemId: "77", format: "pdf" })`
  — valeur exacte, pas seulement "un POST a eu lieu". `itemId: "77"` est
  l'id réellement retourné par la création de carte dans ce run (vérifié via
  `expect(page).toHaveURL(/\/maps\/77$/)` juste avant), `format: "pdf"` est
  bien le bouton "PDF" réellement cliqué (le test ne clique jamais "PNG").
- L'état final "done" est vérifié via le `resultUrl` exact du mock
  (`https://minio.example.test/exports/job-e2e-1.pdf`) comparé à l'attribut
  `href` réel du lien — pas "un lien existe quelque part".
- `pollCount >= 2` est vérifié pour prouver que la boucle de poll a bien
  itéré à travers un état intermédiaire `"running"` avant `"done"`, pas
  qu'une unique réponse "done" immédiate a masqué un court-circuit de la
  boucle.
- Ajout par rapport au skeleton du brief : une assertion
  `expect(page.getByRole("alert")).toHaveCount(0)` avant l'apparition du
  lien, pour couvrir explicitement l'absence d'erreur pendant l'attente.
- Le scénario "capacité désactivée" (Step demandé par le brief) est
  couvert par le second test, avec `exact: true` sur le nom du bouton pour
  éviter toute ambiguïté avec un futur bouton dont le nom contiendrait
  "Exporter" en sous-chaîne.
- Boutons "Exporter"/"PDF" cherchés avec `{ exact: true }` (le brief ne le
  faisait pas) car `getByRole` fait un matching par sous-chaîne par défaut
  dans Playwright — nécessaire pour ne pas risquer une correspondance
  fortuite si le libellé d'un autre bouton venait à contenir "Exporter" en
  préfixe.

## Écart avec le skeleton du brief

- Navigation initiale changée de `/maps/map-1` (id fictif, sans fixture) à
  la création réelle d'une carte via l'UI, atterrissant sur `/maps/77`
  (id réel produit par `mockCore()`) — cohérent avec la convention établie
  par `map-editor.spec.ts`/`dataset-export.spec.ts` de ce dépôt (créer via
  l'UI plutôt qu'injecter du JSON ou naviguer vers un id qui n'existe dans
  aucune route mockée).
- Réutilisation de `mockCore(page)` du dépôt plutôt que de réinventer les
  routes `/instance`/`/configs/by-item/*` à la main — seule la route
  `/instance` est surchargée (pour `exportEnabled`), toutes les autres
  routes nécessaires (création d'item, config de carte) viennent du fixture
  partagé déjà éprouvé par 13+ autres specs.

## Préoccupations

Aucune. Les deux tests passent, la suite complète (94 tests) passe sans
régression, et les assertions ont été délibérément approfondies au-delà du
skeleton du brief sur les points identifiés par la brief comme sensibles
(corps du POST, lien final).

## Rappel — note pour la mise à jour post-exécution de CLAUDE.md (hors périmètre de cette tâche)

Le brief indique qu'après les 14 tâches + revue, `CLAUDE.md` doit gagner une
entrée SP-17a et documenter explicitement l'état réel de deux vérifications
best-effort non bloquantes : le test `@pytest.mark.playwright` de la Tâche 6
et le build Docker de la Tâche 13. Cette tâche 14 ne touche pas à
`CLAUDE.md` (hors périmètre déclaré : "Touches only: shell/e2e/export.spec.ts") —
signalé ici pour que l'étape finale de clôture SP-17a n'oublie pas ce point.
