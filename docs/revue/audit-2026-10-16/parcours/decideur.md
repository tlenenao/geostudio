# Parcours persona : Élu / décideur, mobile (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Scénario : ouvrir un tableau de bord partagé, filtrer par temps puis par emprise, exporter, recevoir une alerte, le tout sur mobile.
Captures : `docs/revue/audit-2026-10-16/parcours/decideur/*.png`. Aucun fichier source édité, rien commité, ni `postgis-test` ni suite de tests.

## 0. Conditions de test

- Compte `bob` (membre du groupe « Elus audit »), Chromium headless Playwright émulant un mobile (390x844, DPR 2, tactile, UA Android, fr-FR, Europe/Paris), `--disable-web-security` et `env-config.js` réécrit côté navigateur en `VITE_AUTH_MODE=oidc` (le conteneur shell sert `mock`, le cœur est en `oidc` : déjà constaté par l'audit « analyste SIG »). Scripts hors dépôt. Rien changé dans la stack.
- Données de test créées via l'API (instance locale, pas de destruction) : collection `ingest_1ee04b6d2a61` « Signalements citoyens (audit decideur) » (800 points, colonnes `date, commune, type, nb`, 4 communes de Corrèze, 92 jours), item dataset `f03e71ac4d714a9aa22128d74a9165b9` (`timeField=date`, `reactsToExtent=true`), app « Signalements - tableau de bord elu (audit) » `21bd8211bc6247a78f7397bc1746e047` (hero, filtre de période, indicateur, graphique, carte, tableau, `interactions: auto`), alerte `8abc895fbed74029b74c834105eba2f7` (`value > 500`, webhook), groupe « Elus audit », un signet « Septembre (audit decideur) ». Alice a partagé app + dataset + collection au groupe (en lecture), voir F1.
- Limite d'environnement : image `geostudio-shell` du 2026-10-11, antérieure au HEAD. Les constats portent sur ce qui tourne ; chaque point renvoie au code HEAD pour confirmation. Pas de fond de carte (tuiles externes inaccessibles : la carte est un aplat orange avec des points noirs, ce n'est pas un défaut produit).
- Mesures : LCP 0,79 à 0,98 s (catalogue, tableau de bord, cloche) ; chargement réseau idle du tableau de bord 0,9 s ; axe-core wcag2a/aa/21aa : 0 violation sur catalogue et tableau de bord ; pas de défilement horizontal de page (scrollWidth = 390). Console : aucune erreur applicative hormis les 401 initiaux (F9) et les 404 de F1.

## 1. Chronologie et notes

| Étape | Durée mesurée | Note /10 | Résumé |
|---|---|---|---|
| 0. Connexion OIDC (mobile) | 1,7 s | 8 | Fluide, catalogue lisible en cartes empilées, barre d'onglets basse. Cibles de la barre du haut 32x32. |
| 1. Trouver et ouvrir le tableau de bord | clic → page 46 ms, idle 0,9 s, LCP 0,79 s | 7 | Rapide. Le catalogue mélange 23 items dont des dizaines de `aud-*` (bruit d'audit). |
| 1b. Même ouverture si le dataset n'est pas partagé | 2,2 s | 2 | Widgets « Erreur de données » sans cause (F1). |
| 2. Lire le tableau de bord | scroll 1277 px | 4 | Un KPI faux (F2), légende `value`, un libellé d'axe sur deux, bandeau tronqué (F5), pas de navigation (F7). |
| 3. Filtrer par temps | 2 saisies de date + 0,5 s ; réseau stable en 3,3 s | 6 | Fonctionne et se répercute (tableau 252/800, graphique, export), puces de contexte persistantes. Pas de plages prédéfinies, sélecteur natif en `mm/dd/yyyy`, KPI non mis à jour (F2). |
| 4. Filtrer par emprise (zoom carte) | 2,7 s, 2 agrégats avec `bbox` | 4 | Filtre actif sans geste de l'utilisateur et appliqué au graphique seulement (F3). |
| 5. Exporter les données (CSV) | 124 ms, 253 lignes | 7 | Respecte la période. Menu ⋮ de 20x16 px, geojson/gpkg proposés à un élu (F6). |
| 6. Exporter la vue (PDF/PNG) | échec après ~3 s, 1 clic | 2 | Échec sur la stack locale (F4) ; de plus l'export ne transmet ni période ni emprise (F4b). |
| 7. Enregistrer la vue / partager | 1,7 s | 7 | Crée un signet, URL `?ctx=` partageable ; l'emprise n'est pas enregistrée (`extent: null`) alors que la puce « Emprise active » est affichée. |
| 8. Recevoir une alerte | évaluation en ~3 s | 2 | Le décideur ne la reçoit pas (F8). |
| 9. Cloche de notifications (mobile) | ouverture 0,3 s | 3 | Panneau débordant de 93 px hors écran, message technique brut (F10). |

Note globale du parcours : 4,4 / 10. Étapes critiques (lire juste, exporter la vue, être alerté) en dessous de 5.

## 2. Blocages (classés)

1. **F8** : un élu partageant une alerte avec un groupe n'en reçoit aucune notification ; seul le propriétaire est notifié, et le webhook interne est bloqué par la garde d'egress.
2. **F2** : le KPI « Signalements » affiche 100 pour 800 (ou 252 après filtre) : chiffre faux sur le premier écran d'un décideur.
3. **F4 / F4b** : l'export PDF/PNG de la vue échoue sur la configuration locale par défaut, et même réussi ne reflète pas les filtres.
4. **F1** : un tableau de bord partagé est vide si le dataset et la collection ne sont pas partagés séparément, avec un message sans cause.
5. **F3** : « filtrer par emprise » ne filtre que le graphique, pas le tableau, le KPI ni l'export.

## 3. Constats détaillés

### F1. Partager l'app ne suffit pas : trois objets à partager, erreurs opaques
Preuve : app seule partagée à `bob` → `GET /v1/configs/by-item/f03e71ac...` 404 (dataset) puis, dataset partagé, `GET /v1/collections/ingest_1ee04b6d2a61/items` 404 `collection not found` (`curl` avec le jeton de bob), jusqu'au partage explicite de la collection. Côté UI : « Erreur » / « Erreur de données » (`02-ouverture.png`), sans indication de droit manquant ni de contact.
Code : 404 volontaire avant 403 `core/app/collections/routes.py:345` ; message unique `shell/src/builder/widgets/chart.tsx:416,445`, `mapWidget.tsx:304`, catalogue `shell/src/i18n/catalog.fr.ts:188` (`common.dataError`). Rien dans le dialogue de partage n'avertit des dépendances (non vérifié dans le code du dialogue, constaté à l'usage via l'API).
Note : bloquant pour le créateur qui publie à un élu, friction forte pour l'élu (aucune action possible de sa part).

### F2. Le KPI compte les lignes chargées (plafond 100), pas le total
Preuve : indicateur `agg: count` sur source `features` : affiche 100 avec 800 entités (`03b-dashboard-pleine-page.png`), et toujours 100 après filtre de période alors que le tableau annonce « 100 sur 252 » (`04-filtre-temps.png`).
Code : `shell/src/builder/widgets/indicator.tsx:186-188` (`data.records.length`) alors que l'état porte `total` (`shell/src/builder/DataContext.tsx` `total: r.data?.total`, issu de `numberMatched`, `shell/src/api/base.ts:538`) et que le widget tableau l'utilise (`widgets/data.tsx:377`). Un KPI sur source `statistics` est correct (même fichier, l.178).
Note : valeur fausse présentée sans avertissement, pour un chiffre-clé.

### F3. Le filtre d'emprise s'active tout seul et ne touche que le graphique
Preuve : après ouverture, la puce « Emprise carte active » apparaît sans geste (auto-cadrage), consommant ~60 px du haut d'écran mobile (`04-filtre-temps.png`) ; après zoom, 2 `POST /aggregate` portent `bbox`, mais tous les `GET /v1/collections/.../items` restent sans `bbox` et le tableau reste à « 100 sur 800 » (`05-emprise-zoom.png`). Le CSV exporté n'a pas non plus de `bbox`.
Code attendu : `shell/src/lib/analyticsPatch.ts:27-29` injecte `bbox` pour toute source du dataset `reactsToExtent`, appliqué par `DataContext.tsx:88` ; le comportement observé contredit cette lecture (cause non isolée : image potentiellement antérieure au HEAD, à rejouer sur image fraîche). Les mêmes `GET` sont aussi émis 5 à 6 fois pour un même état (réseau).
Le signet n'enregistre pas l'emprise (`"extent":null` dans le `POST /v1/configs`, étape 7).

### F4. Export PDF/PNG de la vue : échec, message technique, filtres non transmis
Preuve : `POST /v1/export {"itemId":...,"format":"pdf"}` → job `Échoué` en ~3 s ; message affiché dans la barre : « le cœur (http://localhost:8200)... n'est pas joignable depuis export-worker : Connection refused... Définir VITE_CORE_URL » (`09b-export-pdf-fin.png`), identique dans la cloche. Le message est rédigé pour l'administrateur, pas pour l'élu, et occupe la moitié de l'écran mobile.
Code : `core/app/export/jobs.py:153` (message) ; même cause que F10 de l'audit « analyste SIG » (configuration locale par défaut).
**F4b** : le corps de l'export ne contient que `itemId`, `format` et `entityId/atlas` (`shell/src/api/domains/exportsIngestion.ts:56-61`), jamais la période ni l'emprise ni le signet : le PDF d'un tableau de bord filtré montrera donc la vue non filtrée (déduction du code, non rejouable ici faute d'export réussi). Le bouton « Exporter » du runtime est monté par `AppRuntimePage.tsx:231`.

### F5. Lisibilité mobile du tableau de bord
- Bandeau `hero` tronqué en haut et en bas (`03b-...png`) : `shell/src/builder/widgets/hero.tsx:117` impose `h-full` et `p-8` dans une cellule de hauteur fixe ; un titre sur 2 lignes déborde dès 390 px (ma config : `h: 2`, à relativiser).
- Graphique : légende `value` (nom technique de la mesure du cœur, `core/app/analytics/aggregate.py`), 2 libellés d'axe sur 4 affichés, axe Y compressé (`04-filtre-temps.png`).
- Sélecteurs de date natifs affichés `mm/dd/yyyy` malgré `fr-FR` (rendu Chromium headless, à confirmer sur un vrai mobile) ; aucun raccourci (« 7 jours », « mois en cours ») : `shell/src/builder/widgets/dateRangeFilter.tsx:48-68` n'offre que deux champs libres.
- Carte : la barre d'outils Mesurer/Surface/Effacer/Croquis occupe ~40 % de la hauteur de la carte à 390 px (`05-emprise-zoom.png`) ; un tap au centre n'a ouvert aucun popup (popup non configuré dans mon app, non conclusif).

### F6. Petites cibles tactiles et options inadaptées à un décideur
- Boutons mesurés (390 px) : « Effacer la période » 10x16, « Effacer l'emprise » 10x16, « Explorer » (⋮) 20x16, « Précédent » 70x18 : sous 24x24 px (WCAG 2.5.8 AA), alors qu'axe-core ne le signale pas (règle hors des tags utilisés). Code ⋮ : `shell/src/builder/widgets/ExplorerMenu.tsx:119-127` (`px-1 text-xs`).
- Le menu ⋮ propose « Voir les entités », CSV, XLSX, GeoJSON, GPKG, même sur un indicateur (`08a-menu-explorer-kpi.png`) ; pas de libellé orienté usage (« Télécharger les données du tableau »).
- Réussite : CSV de 253 lignes en 124 ms, nom daté, filtre de période respecté (`GET .../export/items?format=csv&date__gte=...&date__lte=...`), colonne `geometry` en WKT.

### F7. La page runtime n'a ni en-tête, ni cloche, ni retour
Preuve : sur `/apps/:pk`, le texte de la page commence par « Exporter / Enregistrer la vue » ; aucun bouton Notifications ni lien Catalogue (`j9`, `03a-dashboard-haut.png`). Code : la route est hors du layout protégé, `shell/src/shell/routes.tsx:377` (après la fermeture du groupe qui contient `/settings`, l.375). Un élu qui reçoit un lien ne voit donc jamais ses notifications depuis le tableau de bord et ne revient au catalogue que par le bouton « précédent » du navigateur.

### F8. L'élu ne reçoit pas l'alerte
Preuve : alerte partagée en lecture au groupe, évaluation déclenchée (`POST /v1/alerts/{id}/evaluate` 202, évaluation `firing`, valeur 800 en ~3 s, worker OK). Notifications : alice (propriétaire) en a 1 de type `alert`/`failure` ; bob, 0 (seulement l'échec d'export). Le webhook vers une cible interne est refusé : `notifyError: "webhook egress blocked: cible réseau interne bloquée : 'host.docker.internal'"`.
Code : notification in-app uniquement au propriétaire `core/app/alerts/jobs.py:573-595` (`recipient_user_id=owner_id`) ; garde SSRF `core/app/alerts/egress.py` (voulue). L'email exige un secret SMTP créé par un administrateur. Un décideur ne peut ni « s'abonner » à une alerte partagée, ni choisir un destinataire interne ; il peut seulement lire l'historique (`GET /alerts/{id}/evaluations` 200 pour bob).
Note d'écart de rôle : `core/app/users/repository.py:55` attribue le rôle Créateur à tout nouvel utilisateur OIDC (constaté : bob a `data.manage`, `automation.manage`, `maps.manage`). L'élu est donc un Créateur par défaut, ce qui masque le défaut de F8 (il pourrait créer sa propre alerte, hors du parcours « consommateur ») et expose des menus de création (« Nouveau », « Importer un fichier » dans l'en-tête mobile).

### F9. 401 initiaux à chaque ouverture directe
Preuve : à chaque `goto /apps/{id}`, `GET /v1/me` et `GET /v1/items/{id}` partent sans en-tête `Authorization` (≈ 385 ms) et reçoivent 401, puis réussissent à la reprise ; 4 lignes d'erreur console « Failed to load resource 401 ». Sans effet visible, mais bruit dans la console et dans les journaux d'audit/rate-limit.

### F10. Cloche de notifications : débordement mobile et textes techniques
Preuve : panneau ouvert à `left=169, right=483` pour une fenêtre de 390 px (`j11`), « Tout marquer comme lu » et la fin des lignes coupés (`10-cloche.png`). Contenu : l'erreur brute de F4 en rouge. Le filtre « Tous » est un `<select>` natif de 140 px. LCP et axe-core restent bons (0 violation).

## 4. Réussites à conserver

- Ouverture du tableau de bord en moins d'une seconde, aucune violation axe, aucun défilement horizontal à 390 px.
- Puces de contexte (« Période : ... → ... », « Tout effacer ») persistantes en haut, visibles et supprimables.
- Signet avec URL `?ctx=` partageable, le contexte de filtre revient à la réouverture.
- Export CSV rapide et fidèle au filtre de période.
- Cloche : une erreur d'export est bien remontée avec l'item concerné.

## 5. Non rejoué / limites

- PDF/PNG réussi : impossible sans joignabilité cœur depuis `export-worker` ; F4b reste une déduction du code.
- Email d'alerte : pas de secret SMTP ni de serveur SMTP local ; seul le webhook (bloqué) a été éprouvé.
- Alerte récurrente (cron `*/5`) non attendue ; une évaluation manuelle a été utilisée.
- Rôle Lecteur réel non testé (aucun compte admin pour changer le rôle de `bob`) ; les constats F1/F8 valent pour tout rôle.
- Vrai appareil tactile et lecteur d'écran : non testés (limite déjà acceptée dans le dépôt).
- Données de test laissées sur l'instance (liste en §0), sans suppression.
