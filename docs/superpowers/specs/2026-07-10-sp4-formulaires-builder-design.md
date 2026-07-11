# GeoStudio SP-4 — Formulaires dans le builder

> Design / spec. Couvre tout SP-4 tel que défini par la feuille de route
> (« le cran Retool n° 1 » — une app métier qui *écrit*, créée sans code).
> L'exécution se fera en plusieurs plans datés (SP-4a/b/c, §1) — cette spec
> ne préjuge pas du découpage en tâches, seulement de la vision d'ensemble.
>
> Date : 2026-07-10. Statut : design approuvé.
> Prérequis : SP-3 (a livré ; b — CRUD features OGC + RLS — plan écrit,
> pas encore exécuté). Cette spec est écrite contre le contrat déjà
> documenté par le plan SP-3b (`docs/superpowers/plans/2026-07-10-sp3b-features-ogc.md`) :
> `GET/POST/PUT/DELETE /collections/{cid}/items[/{fid}]`, GeoJSON,
> erreurs `400 {"errors":[{field,code,message}]}`, `401/403/404/409`, audit
> `feature.create/update/delete`. Si ce contrat change avant que l'exécution
> de SP-4 démarre, cette spec devra être ajustée en conséquence — ce n'est
> pas un détail d'implémentation mineur.

---

## 1. Contexte, périmètre et sous-phases

La feuille de route (§SP-4) fixe l'objectif : le cas d'usage n° 1 décidé,
une app métier qui écrit, créée sans code. Widget Formulaire généré depuis
le schéma d'une collection (A9), actions du bus `feature.create/update/
delete`/`form.submit`/`form.reset`, sélection→édition (Table/Carte →
Formulaire), rafraîchissement des data sources après écriture, template
« Application de saisie ».

Cette spec couvre l'ensemble ; l'exécution se fera en 3 plans datés, chacun
un incrément testable et livrable seul :

- **SP-4a — Widget Formulaire (création seule).** Rendu depuis le schéma
  introspecté d'une collection (`GET /collections/{id}/schema`, SP-3a) +
  panneau d'overrides visuel (label/ordre/masquage/validation par champ)
  dans le builder + validation client **et** serveur + action
  `feature.create` + `form.reset`. Nouvelles méthodes `ItemClient
  .createFeature/updateFeature/deleteFeature` posées ici (même si seules
  `createFeature`/`form.reset` sont câblées à un widget).
- **SP-4b — Édition depuis sélection.** La Table émet `itemSelected`
  (comme le widget List le fait déjà) ; la Carte émet aussi `itemSelected`
  au clic sur une entité — travail nouveau, elle n'émet aujourd'hui que
  `extentChanged` ; le Formulaire déclare une action `loadRecord` qui
  bascule en mode édition ; `feature.update`/`feature.delete` câblés ;
  invalidation TanStack Query des data sources affectées après toute
  écriture (§5).
- **SP-4c — Intégration et E2E.** Template galerie « Application de
  saisie » (Formulaire + Carte + Table pré-câblés) + spec E2E Playwright
  « déclarer un incident » (critère d'acceptation complet de la feuille de
  route) + vérification UI viewer (boutons d'écriture masqués, 403 serveur
  si forcé).

**Hors périmètre (cette spec entière, pas seulement SP-4a).**
- Gestion de conflit d'édition concurrente (pas d'ETag/If-Match côté
  SP-3b) — dernière écriture gagne, cohérent avec l'absence de moteur de
  workflow décidée pour le projet. Simplification assumée, pas un oubli.
- Variables typées (`record`/`list`) — différé à SP-5 ; le binding
  sélection→édition passe par le bus directement (§3), pas par les
  variables.
- Optimistic update du cache après écriture — invalidation complète
  uniquement (§5).
- Retry automatique sur échec d'une action d'écriture.
- Reprojection CRS, PATCH partiel (`PUT` seulement, remplacement complet) —
  déjà hors périmètre de SP-3b, donc hors périmètre ici aussi.

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Schéma `BuilderConfig` du cœur | Aucun changement. Le Formulaire est un `LayoutItem` (`widget: "form"`) comme tout autre widget — sa config (champs, overrides, `dataSourceId`) vit dans `props: dict`, interprétée côté shell uniquement. |
| Binding aux données | Réutilise le concept `DataSource` existant (`type: "features"`, déjà consommé par `client.queryDataSource`/`client.featuresUrl`) — le Formulaire référence un `dataSourceId` exactement comme Table/Carte le font déjà. Aucun nouveau concept de binding introduit. |
| Contrat d'écriture consommé | Celui déjà spécifié par le plan SP-3b : `POST/PUT/DELETE /collections/{cid}/items[/{fid}]`, `201+Location`/`204`/`204`, erreurs `400 {"errors":[{field,code,message}]}`, `401`/`403` (`"collection is not editable"`)/`404`/`409`. |
| Sélection→édition | Bus direct, pas de variable (les variables restent string-only, `VariablesContext: Record<string,string>` — cf. §3). Table et Carte émettent `itemSelected` avec le `DataRecord` complet ; le Formulaire déclare `actions: ["loadRecord", "reset"]` — même mécanisme que `flyTo`/`highlight` de la carte, qui prouve déjà que le bus transporte des payloads structurés vers une action de widget. |
| Géométrie du champ carte | Point + ligne + polygone dès v1 (décidé en session — plus proche de la parité SIG que le point seul, malgré le travail d'interaction carte supplémentaire). Si l'effort déborde en SP-4a, replier sur point-seul et reporter ligne/polygone à SP-4b sans bloquer la livraison (§7 Risques). |
| Overrides de champ | Panneau visuel complet dès SP-4a (liste des champs introspectés, par champ : label, ordre par glisser-déposer, masquer/afficher, règles de validation requis/min-max/motif) — cohérent avec le critère d'acceptation « app créée en < 15 min sans code ». Stocké dans `props` du `LayoutItem` Formulaire, jamais dans le schéma de la collection (propriété du module `collections`). |
| Validation | Deux couches, mêmes règles, jamais de divergence : client (au blur + au submit, JS pur) et serveur (`app.features.validate_feature`, re-validation complète). Le client ne peut jamais contourner les règles, seulement éviter l'aller-retour dans le cas courant. |
| Rafraîchissement après écriture | Invalidation TanStack Query de toute data source `type: "features"` référençant la même collection (`layer`/`service` identiques), dans tous les widgets de la page — pas seulement celui qui a soumis. Pas de cache partiel, pas d'optimistic update. |
| États de l'action d'écriture | `idle \| pending \| success \| error`, même convention que `isPending`/`isError` + `role="alert"` déjà utilisée sur les pages d'édition existantes (`AppBuilderPage.tsx`, `ItemActions.tsx`). |

## 3. Architecture

```
Table/Carte (widget)
  │ bus.emit(widgetId, "itemSelected", record: DataRecord)
  ▼
ActionBus (existant, ActionBus.ts) — wiring "{from} {event}" → "{to} {action}"
  │ (câblé dans ActionsPanel, comme n'importe quel autre message)
  ▼
Formulaire (widget) — useBusAction(bus, widgetId, "loadRecord", handler)
  → bascule en mode édition, pré-remplit les champs depuis `record.properties`
    (+ `record.geometry` si la collection en a une)
```

Le bus transporte déjà des payloads structurés (pas seulement des chaînes)
vers une action de widget — le widget Carte le fait aujourd'hui pour
`flyTo`/`highlight` (`centerFromPayload`/`geometryFromPayload`,
`mapWidget.tsx`). SP-4 étend ce même mécanisme, il n'en invente pas un
nouveau. Les variables (`VariablesContext`, `initialValue: string`)
restent hors du chemin : un `DataRecord` entier ne peut pas être stocké
dans une variable aujourd'hui (elles sont strictement string), et ce
n'est pas nécessaire ici puisque le bus suffit.

Écriture : le Formulaire appelle `ItemClient.createFeature`/
`updateFeature`/`deleteFeature` (nouvelles méthodes, même famille que
`queryDataSource`/`featuresUrl` déjà présentes sur l'interface), qui
posent `POST`/`PUT`/`DELETE` sur `/collections/{cid}/items[/{fid}]` côté
cœur (contrat SP-3b). Succès → émet `submitted` sur le bus (déclenche le
rafraîchissement §5, peut piloter d'autres widgets) puis repasse en mode
création (`feature.create`) ou reste sur l'enregistrement édité
(`feature.update`). Échec → émet `failed` avec le détail, affiche les
erreurs par champ (400) ou un message générique (409/403/404).

## 4. Validation (client + serveur)

- **Source des règles.** Le schéma introspecté (`GET /collections/{id}
  /schema`) fournit la base : types, `NOT NULL`, valeurs d'énumération. Le
  panneau d'overrides du builder (§2) ajoute des règles déclaratives
  par-dessus (requis, min/max, motif) — stockées dans `props` du
  `LayoutItem` Formulaire.
- **Client.** Validation à la saisie (au blur) et au submit, exécutée en JS
  pur à partir de ces mêmes règles — pas de round-trip serveur pour un
  champ requis vide ou un nombre hors bornes.
- **Serveur.** Re-validation complète par `app.features.validate_feature`
  (déjà spécifiée par le plan SP-3b) au moment du `POST`/`PUT` — le client
  ne peut jamais contourner les règles. Les erreurs serveur
  (`400 {"errors":[{field,code,message}]}`) s'affichent champ par champ, en
  réutilisant le même mapping `field → message` que la validation client.

## 5. Données : rafraîchissement après écriture

Après un `feature.create`/`update`/`delete` réussi, invalidation TanStack
Query de toute data source de type `"features"` référençant la même
collection (`layer`/`service` identiques), dans tous les widgets de la
page — pas seulement celui qui a soumis. C'est la seule règle : pas de
cache partiel, pas d'optimistic update en v1 (un rafraîchissement complet
est largement assez rapide pour les volumes de démo).

## 6. États et erreurs de l'action d'écriture

Le Formulaire expose un état `idle | pending | success | error` :
- `pending` désactive le bouton de soumission ;
- `success` émet `submitted` sur le bus (§5) puis repasse en mode création
  si l'action était `feature.create`, ou reste sur l'enregistrement si
  `feature.update` ;
- `error` émet `failed` avec le détail, affiche les erreurs de champ (400)
  ou un message générique (409/403/404) — pas de retry automatique.

Aucune gestion de conflit d'édition concurrente en v1 : dernière écriture
gagne (§1 Hors périmètre).

## 7. Stratégie de tests

- **Cœur.** Aucun changement — SP-4 est un chantier front pur ; le contrat
  OGC est déjà spécifié et testé par SP-3b.
- **Shell, unitaire.** Rendu du Formulaire depuis un schéma introspecté
  fixe (mock), validation client (règles issues du schéma + overrides),
  mapping des erreurs serveur 400 → affichage par champ, état
  `idle/pending/success/error`, émission/réception `itemSelected`→
  `loadRecord` sur un bus de test.
- **Shell, E2E Playwright** (nouvelle spec — règle du projet : chaque
  feature visible a sa spec E2E). Scénario de référence de la feuille de
  route : créer une app « déclarer un incident » (Formulaire + Carte +
  Table) sans code, créer une entité, la voir apparaître carte+table, la
  modifier depuis la sélection table→formulaire, la supprimer ; un
  `viewer` ne voit pas les boutons d'écriture et une écriture forcée est
  refusée (403).

## 8. Critères d'acceptation

- Une app « déclarer un incident » (formulaire + carte + table) créée dans
  le builder sans code ; en runtime : créer une entité, la voir apparaître
  sur la carte et dans la table, la modifier depuis la sélection
  table→formulaire, la supprimer.
- Un `viewer` ne voit pas les boutons d'écriture et le serveur refuse ses
  écritures (403).
- Validation client et serveur cohérentes : une règle violée est signalée
  à la saisie/au submit côté client, et le serveur refuse aussi
  l'écriture si le client est contourné.
- Après toute écriture réussie, toutes les data sources de la même
  collection se rafraîchissent, sur tous les widgets de la page.

## 9. Risques

- **Le plus gros SP front** (déjà nommé par la feuille de route) : le
  binding sélection→édition est le morceau dur. SP-4a livre d'abord un
  Formulaire autonome (création seule) qui a de la valeur seul, avant
  d'attaquer SP-4b — pas de dépendance à un binding non encore construit
  pour livrer une première tranche utile.
- **Dépendance SP-3b non livrée.** Cette spec est écrite contre le contrat
  déjà documenté dans le plan SP-3b ; si ce contrat change avant que
  l'exécution de SP-4 démarre, cette spec devra être ajustée en
  conséquence.
- **Géométrie point+ligne+polygone dès v1** : plus de travail
  d'interaction carte que le point seul — si l'effort déborde, replier sur
  point-seul pour SP-4a et reporter ligne/polygone à SP-4b sans bloquer la
  livraison.
