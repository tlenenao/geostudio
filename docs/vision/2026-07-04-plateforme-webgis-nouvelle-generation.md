# Plateforme WebGIS nouvelle génération — exploration 2026

> Exercice de conception « feuille blanche » : si nous devions concevoir aujourd'hui la
> meilleure plateforme géospatiale possible avec les technologies 2026, que
> construirions-nous ? L'objectif n'est pas de cloner ArcGIS Enterprise 12.1, mais de
> devenir une alternative crédible en 5 ans, en repartant des besoins réels.
>
> Panel : Principal GIS Architect · Staff Software Architect · Platform Engineer ·
> Product Manager SIG · Expert cloud-native & IA.
>
> Date : 2026-07-04 · Statut : document d'exploration, pas de décision d'implémentation.

---

## Sommaire

1. [Vision produit](#1-vision-produit)
2. [Architecture générale](#2-architecture-générale)
3. [Données](#3-données)
4. [Cartographie](#4-cartographie)
5. [Développement applicatif](#5-développement-applicatif)
6. [IA](#6-ia)
7. [Temps réel](#7-temps-réel)
8. [Déploiement](#8-déploiement)
9. [Sécurité](#9-sécurité)
10. [Exploitation](#10-exploitation)
11. [Analyse comparative](#11-analyse-comparative)
12. [Architecture cible](#12-architecture-cible)

---

## Postulat de départ

Trois hypothèses historiques d'ArcGIS Enterprise méritent d'être remises en cause avant
même d'entrer dans les domaines :

1. **« Les données doivent passer par un serveur pour être servies. »** Faux en 2026.
   Les formats cloud-native (COG, PMTiles, GeoParquet, FlatGeobuf) se servent
   directement depuis un object storage par requêtes HTTP Range. Le serveur devient
   l'exception (transactionnel, sécurité fine), pas la règle. **Le format est l'API.**

2. **« Le SIG est une plateforme à part, où l'on vient travailler. »** Le besoin réel
   est inverse : la capacité géospatiale doit s'intégrer dans les outils où les gens
   travaillent déjà (BI, data platform, applications métier, agents IA). Une plateforme
   qui exige qu'on vienne à elle perd contre une plateforme qui s'exporte.

3. **« La richesse fonctionnelle est le fossé défensif. »** ArcGIS gagne par la largeur
   du catalogue. Mais 80 % des usages tiennent dans 20 % des fonctions, et la largeur a
   un coût : complexité d'exploitation, courbe d'apprentissage, verrouillage. Le fossé
   moderne, c'est la **simplicité d'adoption** (un `docker compose up` qui marche) et
   l'**ouverture** (standards, formats, extensibilité).

---

## 1. Vision produit

### Approche classique

ArcGIS Enterprise se positionne comme *le* système d'information géographique de
l'organisation : un portail central où des professionnels SIG cataloguent, servent,
analysent et publient des données spatiales, avec un écosystème d'applications clientes
(Pro, apps web, apps mobiles) qui gravitent autour. Le modèle économique repose sur des
licences nommées, des rôles types (« user types ») et des extensions serveur payantes.

### Limites

- **Centré sur le professionnel SIG**, alors que 95 % des consommateurs de cartes ne
  sont pas des géomaticiens. Le géomaticien devient goulet d'étranglement.
- **Périmètre en expansion permanente** (BI, imagerie, IoT, knowledge graphs, indoor…)
  qui dilue le produit et alourdit l'exploitation.
- **La donnée appartient à la plateforme** (geodatabase, services propriétaires) plutôt
  que la plateforme ne s'adapte à la donnée. Sortir coûte cher — c'est voulu.
- Modèle de licence complexe qui pénalise justement la démocratisation qu'Esri promeut.

### Approche moderne

Mission proposée : **« rendre la donnée géospatiale utilisable par tous, partout où les
décisions se prennent »**. Concrètement :

- La plateforme est un **hub, pas un silo** : elle catalogue et sert des données qui
  restent dans des formats ouverts, consommables sans elle (un GeoParquet sur S3 reste
  lisible par DuckDB, QGIS, un notebook, un agent IA — plateforme éteinte).
- **Personas cibles**, par ordre de priorité :
  1. **L'agent métier / décideur** (consulte, filtre, alerte) — le volume.
  2. **L'analyste de données** (SQL, notebooks, BI) — le pont vers la data platform,
     persona historiquement mal servi par les SIG.
  3. **Le géomaticien** (qualité, référentiels, cartographie experte) — le garant.
  4. **Le développeur** (SDK, API, plugins) — le multiplicateur.
  5. **L'agent de terrain** (mobile, offline) — le capteur.
- **Cas d'usage prioritaires** (le « 20 % qui sert 80 % ») :
  - publier une donnée et la partager (carte, app, API) en minutes ;
  - construire un tableau de bord / une app métier sans code ;
  - interroger le patrimoine de données en langage naturel ;
  - collecter sur le terrain, y compris hors connexion ;
  - alerter sur événements spatiaux (géofencing, seuils, anomalies).

### Compromis

- Prioriser le consommateur métier, c'est accepter d'être **moins profond** que
  ArcGIS Pro sur l'analyse experte au départ. On assume : QGIS existe, s'interface
  nativement (PostGIS, OGC), et couvre ce besoin — inutile de le réinventer.
- « La donnée reste ouverte » réduit le verrouillage, donc la rétention forcée. La
  rétention doit venir de la valeur (UX, IA, collaboration), pas du coût de sortie.
  C'est un pari commercial autant que technique.

### Recommandation

Positionner le produit comme **la couche géospatiale de la data platform moderne**, pas
comme un SIG monolithique concurrent frontal. Cibles initiales : collectivités et
organisations de taille moyenne étranglées par le coût/complexité d'ArcGIS Enterprise,
et équipes data qui veulent du géospatial sans adopter un « monde SIG » séparé.

---

## 2. Architecture générale

### Approche classique

ArcGIS Enterprise = fédération de machines et de rôles : Portal for ArcGIS + ArcGIS
Server (déclinable en rôles GIS/Image/GeoEvent/GeoAnalytics/Notebook/Knowledge…) +
ArcGIS Data Store (relationnel, tile cache, spatiotemporel) + Web Adaptors. Chaque rôle
est un quasi-produit, avec sa fédération, ses certificats, ses sauvegardes. La version
Kubernetes existe mais réplique en conteneurs la même complexité (dizaines de pods dès
l'installation de base).

### Limites

- **Complexité d'exploitation disproportionnée** : la fédération Portal/Server est une
  source notoire d'incidents (certificats, tokens, désynchronisation). Le « highly
  available » multiplie les machines.
- Découpage en rôles hérité de l'histoire produit (chaque rôle = un ancien produit
  racheté ou dérivé), pas d'une analyse des frontières de domaine.
- Empreinte minimale énorme : impossible de faire tourner « un petit ArcGIS » sur une
  VM modeste ou en edge.

### Approche moderne

Trois options examinées :

| Option | Description | Verdict |
|---|---|---|
| **Monolithe** | Un binaire unique (style PocketBase/Supabase-single-node) | Séduisant en edge, mais mélange des profils de charge incompatibles (tiling CPU-bound vs API latency-bound) |
| **Microservices** | Découpage fin par capacité | Sur-ingénierie pour une équipe < 50 devs ; le réseau devient le problème ; coût opérationnel élevé |
| **Monolithe modulaire + satellites** | Un cœur unique aux modules à frontières strictes, plus 2-3 services séparés uniquement là où le profil de charge l'exige | **Recommandé** |

Le découpage retenu ne suit pas l'organigramme historique d'Esri mais les **profils de
charge** :

- **Cœur (monolithe modulaire)** : catalogue/métadonnées, identité & permissions,
  builder & configs d'apps, API OGC, partage. Stateless, scalable horizontalement,
  déployable en un seul conteneur.
- **Satellite « compute »** : traitements lourds asynchrones (import/ETL, génération de
  tuiles, analyses batch) — file de jobs + workers éphémères, dimensionnés à zéro au
  repos.
- **Satellite « streaming »** (optionnel, activable) : ingestion temps réel,
  géofencing (§7).
- **État** : PostgreSQL/PostGIS (transactionnel + catalogue) et object storage S3
  (tout le reste). **Deux systèmes d'état, pas cinq.** Pas de « Data Store » maison.

### Compromis

- Le monolithe modulaire exige une **discipline de frontières** (modules à interfaces
  explicites, interdiction d'imports croisés) sinon il pourrit en « big ball of mud ».
  Outillage nécessaire (lint d'architecture, tests de dépendances).
- Extraire un module en service séparé plus tard reste possible si les frontières ont
  tenu — c'est le pari : **on paie le coût du découpage réseau seulement quand une
  frontière l'exige**, pas par anticipation.
- Deux systèmes d'état = quelques cas moins optimaux (le cache de tuiles en S3 est plus
  lent qu'un cache disque local — compensé par CDN/proxy-cache).

### Recommandation

**Monolithe modulaire + workers de jobs + (option) service de streaming**, avec pour
test d'acceptation architectural : *la plateforme complète doit démarrer avec un
`docker compose up` sur une VM 4 vCPU / 8 Go et servir un usage départemental réel*.
Cette contrainte de « scale-down » est le meilleur garde-fou anti-complexité — c'est
exactement ce qu'ArcGIS Enterprise ne sait pas faire.

---

## 3. Données

### Approche classique

Le monde ArcGIS : geodatabase d'entreprise (schéma `sde` sur SGBD), données « publiées »
en services (feature services, map services), caches de tuiles propriétaires, imagerie
via mosaic datasets, métadonnées dans le portail. La donnée n'existe pour la plateforme
que si elle a été *enregistrée puis publiée* ; chaque étape crée une copie ou une
indirection propriétaire.

### Limites

- **La publication est une friction artificielle** : la donnée est déjà là (PostGIS,
  S3, fichiers), pourquoi un rite de passage ?
- Formats propriétaires (geodatabase, caches compacts, SLPK…) = verrouillage et
  invisibilité pour l'écosystème data (Spark, DuckDB, dbt, notebooks).
- Analytique faible : les feature services paginés à 2000 objets sont une API
  transactionnelle qu'on maltraite pour de l'analytique. Le monde BI/lakehouse est
  traité comme étranger.
- Métadonnées portail non standardisées (ni STAC, ni DCAT natif complet).

### Approche moderne

Architecture de données à **deux températures + un catalogue** :

**1. Chaud — opérationnel : PostGIS.**
Source de vérité transactionnelle : données éditées, référentiels vivants, collecte
terrain. PostGIS est le meilleur SGBD spatial du marché, point. On l'expose en
OGC API Features (lecture/écriture), et on capte les changements par CDC (logical
replication) pour alimenter le reste.

**2. Froid — analytique : lakehouse ouvert sur object storage.**
- **GeoParquet** (+ Apache Iceberg pour les tables versionnées/partitionnées) : format
  pivot analytique. Lisible par DuckDB, Spark, Sedona, pandas/GeoPandas, QGIS.
- **COG** (Cloud-Optimized GeoTIFF) pour les rasters, **Zarr** pour les cubes
  multidimensionnels (météo, climat).
- **PMTiles** pour les tuiles vectorielles/raster pré-calculées : un seul fichier sur
  S3, servi par HTTP Range, zéro serveur de tuiles pour le statique.
- **FlatGeobuf** pour le streaming de features et les échanges.
- DuckDB (+ extension spatiale) comme **moteur de requête embarqué** : côté serveur
  pour l'API analytique, et côté navigateur (DuckDB-WASM) pour l'exploration locale de
  GeoParquet — l'analytique sans aller-retour serveur.

**3. Catalogue : STAC étendu.**
STAC pour tout ce qui est spatiotemporel (pas seulement l'imagerie : la communauté
converge vers STAC comme catalogue générique d'assets géo), complété par DCAT pour
l'interop open-data. Le catalogue référence les assets **là où ils sont** — il ne les
possède pas. Enregistrer ≠ copier.

**4. Vecteurs sémantiques : pgvector.**
Embeddings des métadonnées (et de résumés de contenu) dans pgvector pour la recherche
sémantique (§6). Pas de base vectorielle dédiée tant que < dizaines de millions de
vecteurs — un composant d'état en moins.

### Compromis

- **Deux copies de certaines données** (PostGIS chaud + GeoParquet froid) : coût de
  stockage et pipeline de synchro (CDC → compaction). Assumé : c'est le prix standard
  de la séparation OLTP/OLAP, et l'object storage est bon marché.
- **Fraîcheur** : le lakehouse est en retard de minutes sur l'opérationnel. Acceptable
  pour l'analytique ; le temps réel passe par un autre chemin (§7).
- Iceberg ajoute de la machinerie (catalogue de tables). Option simple : GeoParquet
  plat + convention de partitionnement, Iceberg seulement quand le besoin de
  time-travel/schema-evolution est réel.

### Recommandation

**PostGIS pour le chaud, GeoParquet/COG/PMTiles sur S3 pour le froid, STAC comme
catalogue fédérateur, DuckDB comme moteur analytique embarqué, pgvector pour le
sémantique.** Règle d'or : *aucun octet de donnée utilisateur dans un format que QGIS,
DuckDB ou un `curl` ne peut pas lire*.

---

## 4. Cartographie

### Approche classique

Rendu historiquement côté serveur (map services dynamiques, caches de tuiles raster),
puis tuiles vectorielles ; API JavaScript propriétaire riche mais fermée ; 3D via scene
services et format I3S ; styles dans des specs propriétaires ; impression via services
d'export dédiés.

### Limites

- Le rendu dynamique côté serveur est coûteux, difficile à mettre en cache et n'a plus
  de justification pour 90 % des cas depuis les tuiles vectorielles stylées client.
- API JS propriétaire = compétences non transférables, coût de sortie élevé.
- I3S vs 3D Tiles : la guerre des formats 3D est finie, 3D Tiles (OGC) a gagné
  l'écosystème hors Esri.
- Le temps réel cartographique (positions, capteurs) reste un ajout tardif, pas un
  citoyen de première classe.

### Approche moderne

- **MapLibre GL JS** comme moteur de rendu par défaut : rendu GPU, écosystème énorme,
  et la **spec de style MapLibre** comme format de style pivot de la plateforme (les
  styles sont des documents versionnables, éditables par le builder et par l'IA).
- **Tuiles vectorielles partout** : statiques en PMTiles sur S3 ; dynamiques (données
  chaudes PostGIS) via un tiler léger type **Martin** (Rust, MVT à la volée depuis
  PostGIS). Génération planétaire par Planetiler/Tippecanoe dans les workers.
- **OGC API** comme surface de service : Features (vecteur transactionnel), Tiles,
  Styles, Processes (traitements), EDR (environnemental). Compatibilité WMS/WFS en
  lecture pour l'héritage, sans investissement nouveau.
- **3D** : 3D Tiles (OGC) pour maquettes/mesh/nuages de points, terrain quantized-mesh,
  rendu via MapLibre (3D en progrès rapide depuis la fusion des efforts maplibre-gl +
  écosystème deck.gl) avec **CesiumJS en option** pour les cas globe/photogrammétrie
  lourds. **deck.gl** en couche d'analyse pour les grandes volumétries (millions de
  points, trajectoires, hexbins GPU).
- **Temps réel cartographique natif** : couches « live » alimentées en
  WebSocket/SSE (§7), interpolation de positions côté client.
- **Cartographie assistée** : la symbologie, les palettes, les étiquettes sont des
  suggestions IA vérifiables (§6) — la carte par défaut doit être *belle et juste*
  (classification, contraste, accessibilité daltonisme) sans expert.

### Compromis

- MapLibre est en retard sur l'API JS d'Esri pour certains raffinements (étiquetage
  complexe, 3D intégrée mature). On accepte un delta fonctionnel court terme contre
  l'ouverture ; deck.gl/CesiumJS comblent les extrêmes.
- Abandonner le rendu serveur dynamique généralisé : quelques cas (cartes très riches
  en couches raster à la demande, impression haute fidélité) nécessitent un rendu
  serveur — on le garde comme *service d'impression/export* ciblé (QGIS Server
  headless fait très bien ce travail), pas comme voie de service principale.

### Recommandation

**MapLibre + style spec ouverte + PMTiles/Martin + OGC API + 3D Tiles**, deck.gl pour
l'analytique visuelle, QGIS Server cantonné à l'impression professionnelle. Le style
devient un artefact de première classe (versionné, diffable, générable par IA).

---

## 5. Développement applicatif

### Approche classique

Chez Esri : Experience Builder (builder no-code à widgets), Dashboards, StoryMaps,
Survey123, Field Maps… chaque usage a *son* builder et *son* runtime. Extensibilité par
widgets custom (jimu, React figé à une version), déploiement de widgets laborieux, pas
de vraie marketplace tierce.

### Limites

- **Fragmentation** : N builders, N modèles de config, N runtimes à maintenir et à
  apprendre.
- Widgets custom couplés à une version de framework imposée ; mise à jour douloureuse.
- Frontière no-code → code abrupte : quand le builder ne suffit plus, on repart de zéro
  avec le SDK.
- Écosystème fermé : pas de distribution tierce viable, pas de modèle économique pour
  les développeurs externes.

### Approche moderne

- **Un seul modèle : tout est une config déclarative rendue par un runtime unique.**
  Une app, un dashboard, une story, un formulaire terrain = le même `AppConfig`
  (layout, widgets, sources de données, actions inter-widgets, thème), rendu par un
  `AppRenderer(config, mode)` en modes édition/aperçu/exécution. Un builder, plusieurs
  *templates de départ* — pas plusieurs produits.
- **Continuum no-code → low-code → code** :
  1. builder visuel (grille responsive, panneau de propriétés, câblage
     triggers→actions) ;
  2. **la config est du JSON lisible, versionnable, éditable à la main et par l'IA** —
     le low-code, c'est éditer la config, pas apprendre un langage maison ;
  3. *eject* propre : toute app peut s'exporter en projet code (SDK) quand elle dépasse
     le builder.
- **SDK fondé sur les standards du web** : composants **Web Components** (utilisables
  depuis React/Vue/Svelte/vanilla), clients TypeScript typés générés depuis OpenAPI,
  hooks de données. Pas de framework imposé côté hôte.
- **Plugins = modules ES + manifeste**, chargés dynamiquement, sandboxés (permissions
  déclarées : quelles APIs, quelles données), versionnés semver contre une API de
  plugin stable et étroite. Le widget tiers ne peut pas casser la plateforme.
- **Marketplace** : registre de plugins/templates/styles signés (sigstore ou
  équivalent), gratuit ou payant, avec revue automatisée (statique + sandbox). C'est
  l'aimant à écosystème — la seule stratégie viable contre un catalogue Esri de 25 ans.

### Compromis

- « Un seul runtime pour tout » risque le plus-petit-dénominateur : un formulaire
  terrain offline et un dashboard temps réel ont des besoins différents. Mitigation :
  le runtime est modulaire (le mode offline est une capacité du runtime, pas un autre
  produit) ; on accepte que 5 % des cas extrêmes passent en SDK.
- Le sandboxing sérieux de plugins (iframe/ShadowRealm/permissions) coûte en
  performance et en complexité d'API. Alternative assumée pour démarrer : plugins
  *trusted* revus + permissions déclaratives, sandbox dur plus tard.

### Recommandation

**Un builder unique config-driven, une config JSON ouverte comme contrat central, SDK
Web Components + TypeScript, plugins ES modules avec manifeste de permissions,
marketplace signée.** La config déclarative est l'actif stratégique : c'est elle que
l'IA lit et écrit (§6), c'est elle qu'on versionne en Git, c'est elle qui survit aux
refontes de runtime.

---

## 6. IA

### Approche classique

Dans les plateformes SIG actuelles : IA = GeoAI (deep learning sur imagerie, modèles
préentraînés), plus des assistants naissants bolt-on (aide à la doc, quelques
copilotes en beta). L'IA est une *fonctionnalité* périphérique, pas une couche
d'architecture.

### Limites

- Les assistants plaqués sur des APIs non prévues pour eux hallucinent des paramètres
  et ne peuvent pas agir de bout en bout.
- Pas de recherche sémantique réelle sur le patrimoine (la recherche portail reste du
  mot-clé).
- Aucune traçabilité : que faisait l'agent, avec quels droits, sur quelles données ?

### Approche moderne

Principe : **l'IA est un client de première classe de la plateforme, avec les mêmes
APIs et les mêmes permissions que les humains.** Concrètement :

- **Surface agentique native : MCP.** La plateforme expose un serveur MCP (Model
  Context Protocol) couvrant catalogue, requêtes, styles, builder, admin. Tout agent
  (le nôtre ou celui du client) peut opérer la plateforme. C'est le prolongement
  naturel de « la config est l'API ».
- **Copilot utilisateur** : « montre-moi les parcelles inondables à moins de 500 m
  d'une école » → l'agent compose requête spatiale + carte + symbologie, **en montrant
  son travail** (la requête SQL/OGC générée est visible, éditable, sauvegardable). Le
  langage naturel est une *entrée*, jamais une boîte noire.
- **Copilot administrateur** : diagnostic (« pourquoi ce service est lent ? » →
  corrélation métriques/traces), politiques de permissions en langage naturel
  compilées vers le moteur ABAC (§9), revue de sécurité des partages.
- **Copilot développeur** : génération de configs d'apps, de styles MapLibre, de
  plugins ; possible précisément parce que tout est déclaratif et documenté par
  schémas JSON.
- **Agents spécialisés SIG** : QA de données (géométries invalides, incohérences
  topologiques, doublons), enrichissement de métadonnées (résumés, mots-clés, lignage
  proposé), extraction sur imagerie (via modèles de fondation type SAM/segmentation),
  géocodage/désambiguïsation d'adresses.
- **Recherche sémantique** : embeddings des métadonnées + résumés de contenu dans
  pgvector, recherche hybride (BM25 + vecteur + filtre spatial/temporel). « Trouve des
  données sur le risque incendie autour de Tulle » doit marcher.
- **Gouvernance IA intégrée** : chaque action d'agent est journalisée (qui, quoi,
  périmètre, coût), les copilotes héritent des permissions de l'utilisateur (jamais
  plus), et le fournisseur de modèle est **enfichable** (API compatible, modèles
  hébergés ou locaux via vLLM/Ollama) — exigence dure pour le secteur public européen.

### Compromis

- Coût d'inférence et variabilité : les copilotes doivent dégrader proprement (la
  plateforme reste 100 % utilisable sans IA) et les actions coûteuses passent par
  confirmation.
- L'évaluation continue (les suggestions de carte sont-elles *justes* ?) est un vrai
  chantier d'ingénierie, pas un détail — budget à prévoir dès le départ.
- Le pari MCP : jeune, mais déjà standard de fait ; le risque de miser dessus est
  faible comparé au risque de bâtir une surface agentique propriétaire.

### Recommandation

**Faire de l'architecture elle-même une architecture « AI-ready »** (tout déclaratif,
tout schématisé, tout journalisé, permissions unifiées) plutôt que de saupoudrer des
chatbots. Le serveur MCP et la recherche sémantique sont les deux premières briques ;
les copilotes par persona s'appuient dessus. Modèles interchangeables, souveraineté
possible.

---

## 7. Temps réel

### Approche classique

ArcGIS GeoEvent Server (produit séparé, lourd, licence dédiée) ou ArcGIS Velocity
(cloud only) : connecteurs d'ingestion, filtres/processeurs en pipeline GUI, sorties
vers feature layers « stream ». Puissant mais opaque, cher, et à part du reste.

### Limites

- Produit séparé = duplication (sécurité, monitoring, montée de version) et couplage
  faible avec le reste (les données temps réel ne sont pas des données comme les
  autres).
- Dimensionné pour le gros IoT alors que la majorité des besoins réels sont modestes
  (quelques centaines de véhicules, des capteurs de crue, des alertes).

### Approche moderne

Échelle progressive, trois paliers :

1. **Palier 0 — inclus dans le cœur** : ingestion HTTP/MQTT simple → PostGIS (table
   des dernières positions + historique), diffusion aux clients en **SSE/WebSocket**,
   couches « live » MapLibre. Suffit à 70 % des cas (flottes, capteurs lents).
2. **Palier 1 — service streaming activable** : broker **NATS JetStream** (léger,
   un binaire — cohérent avec notre contrainte scale-down) ; géofencing comme
   **requêtes continues** (zones = tables PostGIS, moteur d'évaluation en streaming),
   fenêtres temporelles, détection de seuils/anomalies.
3. **Palier 2 — gros débits** : Kafka/Redpanda + traitement (Arroyo/Flink) quand les
   volumes l'exigent. Hors périmètre produit standard ; documenté comme architecture
   de référence.

Les **alertes** sont un objet de première classe transversal (pas seulement temps
réel) : règle (spatiale/attributaire/temporelle) → canaux (email, webhook, push,
Slack/Teams) → journal. Le géofencing n'est qu'un type de règle.

L'historique temps réel est déversé en continu vers le lakehouse (GeoParquet
partitionné par temps) : le replay et l'analyse a posteriori sont gratuits par
construction.

### Compromis

- Ne pas embarquer Kafka par défaut = renoncer au badge « big data » en démo, mais
  épargner à 95 % des clients un cluster qu'ils ne sauront pas opérer.
- Le géofencing en requêtes continues sur PostGIS a un plafond (dizaines de milliers
  d'objets mobiles × zones) ; au-delà, index spatial en mémoire dans le service
  streaming (H3/S2). Concevoir l'API des règles pour que l'implémentation puisse
  changer dessous.

### Recommandation

**Temps réel intégré et progressif : SSE natif dans le cœur, NATS + géofencing en
service activable, Kafka en architecture de référence documentée seulement.** Les
alertes comme capacité produit transversale, pas comme sous-produit IoT.

---

## 8. Déploiement

### Approche classique

Installateurs Windows/Linux, machines dédiées par rôle, Web Adaptors, patchs
trimestriels manuels, dimensionnement à l'avance. ArcGIS Enterprise on Kubernetes
existe mais reste lourd (empreinte de base élevée, opérateur propriétaire) et ne
couvre pas le bas du spectre.

### Limites

- Coût d'entrée opérationnel énorme : il faut une équipe pour *installer* la
  plateforme avant d'avoir produit la moindre valeur.
- Pas de continuum : la version « petite » et la version « HA » sont des mondes
  différents.
- L'edge/embarqué (véhicule, site isolé, bateau) est hors de portée.

### Approche moderne

**Un seul artefact (images OCI), quatre profils de déploiement :**

| Profil | Cible | Forme |
|---|---|---|
| **Solo** | Démo, edge, petite commune, véhicule | `docker compose up` — cœur + PostGIS + MinIO sur une VM/box. Objectif : < 5 min, < 8 Go RAM |
| **Standard** | Département, ETI | Compose/K8s léger (k3s), objet storage managé, sauvegardes automatisées |
| **Scale** | Région, opérateur | Helm chart officiel, HPA sur le cœur, workers autoscalés à zéro, CDN devant les tuiles |
| **Edge sync** | Terrain déconnecté | Cœur en mode allégé + synchronisation différée (données + configs) vers l'instance mère |

Principes :

- **SQLite spatial en mode Solo ?** Non — PostGIS partout, même en solo (un conteneur
  Postgres n'est plus un fardeau) ; l'uniformité vaut plus que les mégaoctets. En
  revanche le client mobile/terrain embarque SQLite/GeoPackage pour l'offline.
- **Cloud-agnostique strict** : dépendances = Postgres + S3-compatible + OIDC. Tout
  cloud, tout on-premise, souveraineté OK.
- **Mises à jour** : migrations automatiques au démarrage, images versionnées semver,
  canal LTS. La montée de version doit être un non-événement.
- **Offline-first terrain** : synchronisation bidirectionnelle basée sur des journaux
  de changements (CRDT ou last-write-wins paramétrable par couche) — capacité cœur,
  pas produit annexe.

### Compromis

- Supporter 4 profils = matrice de test plus large. Mitigé par l'artefact unique et
  des tests d'installation automatisés par profil en CI.
- Ne pas fournir d'opérateur K8s maison au début (Helm suffit) : moins « enterprise »
  sur le papier, beaucoup moins de code à maintenir.

### Recommandation

**Le `docker compose up` en 5 minutes est une exigence produit de niveau 1**, au même
titre qu'une fonctionnalité cartographique. C'est l'arme d'adoption principale contre
un ArcGIS Enterprise qui se déploie en semaines. Le chemin Solo → Scale doit être une
montée en charge, jamais une migration.

---

## 9. Sécurité

### Approche classique

Portal-centrique : utilisateurs/groupes/rôles du portail, partage d'items par
groupes/organisation/public, fédération SAML/OIDC possible, sécurité fine par service
inégale (row-level via des vues ou des « ownership-based access »), multi-tenant
approximé par des portails séparés.

### Limites

- Le modèle de partage par items est bon (à garder !) mais le moteur dessous est
  ad hoc : pas de langage de politique, pas d'audit unifié, ABAC quasi absent.
- Multi-tenant réel impossible sans multiplier les installations.
- La sécurité au niveau de la donnée (ligne/colonne/emprise spatiale) est bricolée.

### Approche moderne

- **Identité déléguée, jamais réinventée** : OIDC natif, **Keycloak** (ou Zitadel)
  comme IdP par défaut embarqué, fédération entreprise (AD/SAML/OIDC) via l'IdP.
  La plateforme ne stocke pas de mots de passe.
- **Multi-tenant de conception** : `tenant_id` dans chaque table et chaque politique
  dès le premier jour (même si 90 % des déploiements sont mono-tenant) — le
  rétrofit est quasi impossible, l'anticipation est quasi gratuite.
- **Autorisation = RBAC pour la simplicité + ReBAC/ABAC pour la finesse** :
  - rôles simples par défaut (viewer/editor/admin par espace de travail) — l'UX de
    partage reste aussi simple qu'aujourd'hui ;
  - dessous, un **moteur de politiques dédié** — deux options crédibles :
    **OpenFGA** (ReBAC à la Zanzibar : « X est éditeur de l'item Y hérité du groupe
    Z ») ou **Cedar/OPA** (ABAC par attributs : « accès si `user.dept ==
    layer.dept` et emprise ⊂ territoire »). Recommandation : OpenFGA pour le
    partage/héritage (c'est structurellement du graphe), attributs spatiaux évalués
    dans la couche donnée ;
  - **sécurité niveau donnée poussée dans PostGIS** : row-level security générée
    depuis les politiques (filtre par attribut ET par emprise spatiale — « cet agent
    ne voit que sa commune »), masquage de colonnes. La donnée filtrée à la source,
    pas dans l'API.
- **Zero Trust pragmatique** : mTLS interservices (mesh optionnel, pas requis),
  tokens courts, principe du moindre privilège pour les jobs/workers, secrets via
  standard externe (Vault/SOPS), **audit log unifié et infalsifiable** (humains,
  APIs, agents IA — même journal).

### Compromis

- Un moteur de politiques externe (OpenFGA) = un composant d'état de plus, en tension
  avec notre minimalisme. Alternative pour le profil Solo : implémentation embarquée
  du même modèle (les politiques sont les mêmes, le moteur est in-process).
- L'ABAC spatial (filtrer par emprise) coûte à l'exécution ; il faut des index et du
  cache de décision. On l'assume : c'est un différenciateur réel pour le secteur
  public (délégations territoriales).

### Recommandation

**OIDC + Keycloak, multi-tenant natif, partage simple en surface / ReBAC dessous
(OpenFGA ou équivalent embarqué), RLS PostGIS générée pour la sécurité niveau
donnée, audit unifié incluant les agents IA.** Le modèle mental utilisateur d'ArcGIS
(items partagés à des groupes) est conservé — c'est le moteur qu'on remplace.

---

## 10. Exploitation

### Approche classique

Administration par consoles web (Portal Admin, Server Manager), logs par composant,
monitoring via un produit séparé (ArcGIS Monitor), sauvegardes par outils dédiés
(WebGISDR), configuration semi-manuelle difficilement reproductible.

### Limites

- L'état de la plateforme n'est pas descriptible : impossible de recréer un
  environnement à l'identique, de « diff » la prod et la préprod, de faire de la
  revue de changement d'infra.
- Observabilité fragmentée et propriétaire.
- L'admin est un métier à part entière — coût humain permanent.

### Approche moderne

- **Tout l'état de configuration est déclaratif et exportable** : politiques,
  tenants, sources de données, apps, styles = des documents (JSON/YAML) applicables
  par API et par CLI. Conséquences immédiates : **GitOps natif** (la config de
  l'instance vit dans Git, appliquée par CI ou par opérateur Flux/Argo),
  environnements reproductibles, promotion dev→préprod→prod par merge request.
- **OpenTelemetry de bout en bout** (traces, métriques, logs structurés) émis
  nativement ; la plateforme n'impose pas la stack d'observabilité (Grafana/Loki/
  Tempo en référence, Datadog si le client préfère). Dashboards et alertes types
  fournis.
- **SLO packagés** : latence tuiles, latence API Features, fraîcheur CDC, backlog de
  jobs — avec alertes préconfigurées. L'exploitant sait *quoi* regarder dès le
  premier jour.
- **Auto-administration** : sauvegardes automatiques testées (restauration vérifiée
  périodiquement), rétention et compaction du lakehouse automatiques, tâches de
  maintenance PostGIS (VACUUM, index) pilotées par la plateforme.
- **Copilot administrateur** (§6) branché sur les traces : diagnostic guidé,
  détection d'anomalies de charge, recommandations de dimensionnement.

### Compromis

- Le « tout déclaratif » impose une rigueur d'API (chaque objet doit être
  exportable/applicable de façon idempotente) qui ralentit un peu chaque feature.
  C'est un coût de conception permanent, remboursé à chaque incident et chaque
  migration.
- Fournir des dashboards types pour une stack qu'on n'impose pas = maintenance de
  plusieurs formats. On privilégie Grafana en premier, export OTLP standard pour le
  reste.

### Recommandation

**Configuration 100 % déclarative + GitOps natif + OpenTelemetry + SLO fournis.**
L'objectif mesurable : une instance Standard exploitable par **0,2 ETP** non
spécialiste SIG — contre plusieurs ETP spécialisés pour un ArcGIS Enterprise HA.

---

## 11. Analyse comparative

### Ce que je garderais (les idées fortes des plateformes actuelles)

1. **Le modèle « item » du portail** : tout (donnée, carte, app, style) est un objet
   catalogué, décrit, partageable, avec propriétaire et cycle de vie. C'est la
   meilleure idée d'ArcGIS — on la garde, adossée à STAC/DCAT.
2. **La carte web comme document** : une webmap déclarative réutilisable dans N
   applications. Généralisée chez nous à *tout* est un document déclaratif.
3. **Le continuum consommation** : la même donnée servie en carte, en app, en API,
   en export — sans que l'utilisateur pense « service ».
4. **Le partage simple** (privé → groupe → organisation → public) : modèle mental
   limpide, à conserver tel quel en surface.
5. **L'intégration bout-en-bout terrain → bureau** (collecte, formulaires, offline) :
   la vraie force d'Esri face aux outils fragmentés.
6. **La galerie de templates/basemaps de qualité** : le time-to-first-map court.
7. De **GeoNode/GeoServer** : la conviction standards ouverts d'abord ; de **QGIS** :
   la preuve qu'une communauté open source peut battre le propriétaire en profondeur
   fonctionnelle.

### Ce que je supprimerais

1. **La fédération Portal/Server** et la notion même de « rôles serveur » à installer
   — remplacée par des modules d'un même cœur.
2. **Le rite de publication** (enregistrer une source → publier un service → gérer le
   service) : la donnée référencée est immédiatement servable.
3. **Les map services dynamiques raster** comme voie par défaut — reliques du rendu
   serveur.
4. **Les formats propriétaires** : geodatabase fichier/entreprise comme format
   plateforme, caches compacts, I3S (3D Tiles a gagné), styles propriétaires.
5. **La multiplication des builders/apps** (Experience Builder + Dashboards +
   StoryMaps + Instant Apps + Web AppBuilder…) → un seul runtime config-driven.
6. **GeoEvent/Velocity comme produits séparés** → temps réel intégré progressif.
7. **Le licensing par utilisateur nommé/user types/extensions** : friction
   commerciale qui contredit la démocratisation. Modèle alternatif : open core +
   support + fonctionnalités d'échelle (SSO avancé, HA, marketplace) payantes.
8. **Les web adaptors** et autres artefacts d'une époque pré-reverse-proxy.

### Ce que j'ajouterais (ce qui manque aujourd'hui)

1. **Le lakehouse géospatial natif** : GeoParquet/Iceberg comme citoyens de première
   classe, DuckDB embarqué, pont naturel vers dbt/Spark/notebooks — le SIG rejoint
   la data platform au lieu de l'ignorer.
2. **La surface agentique (MCP) et les copilotes par persona**, avec gouvernance
   (permissions héritées, audit, modèles interchangeables).
3. **La recherche sémantique** sur le patrimoine de données.
4. **GitOps natif** : toute la plateforme descriptible, versionnable, promouvable.
5. **Le profil « Solo » edge/offline** : la plateforme entière sur une VM ou une box
   de terrain, avec synchronisation différée.
6. **Les alertes comme objet transversal** (règles spatiales/attributaires/
   temporelles → canaux), pas comme sous-produit IoT.
7. **Une marketplace ouverte signée** avec un vrai modèle pour les développeurs
   tiers.
8. **L'analytique dans le navigateur** (DuckDB-WASM sur GeoParquet) : exploration de
   millions d'objets sans serveur.
9. **La sécurité spatiale** (ABAC par emprise : « chacun voit son territoire »)
   générée jusqu'au niveau ligne dans la base.
10. **Des SLO et une exploitabilité packagés** — l'exploitation comme feature.

### Synthèse des recommandations par domaine

| Domaine | Recommandation clé |
|---|---|
| Vision | Couche géospatiale de la data platform, pas SIG-silo ; consommateur métier d'abord |
| Architecture | Monolithe modulaire + workers ; test d'acceptation « une VM 8 Go » |
| Données | PostGIS (chaud) + GeoParquet/COG/PMTiles sur S3 (froid) + STAC + DuckDB + pgvector |
| Cartographie | MapLibre + style spec ouverte + Martin/PMTiles + OGC API + 3D Tiles |
| Applicatif | Un runtime config-driven unique, SDK Web Components, plugins ES + marketplace signée |
| IA | Architecture AI-ready (MCP, tout déclaratif), copilotes par persona, modèles enfichables |
| Temps réel | SSE natif → NATS activable → Kafka documenté ; alertes transversales |
| Déploiement | 4 profils, un artefact ; `docker compose up` < 5 min comme exigence produit |
| Sécurité | OIDC/Keycloak, multi-tenant natif, ReBAC (OpenFGA) + RLS spatiale PostGIS |
| Exploitation | Déclaratif + GitOps + OpenTelemetry + SLO fournis ; cible 0,2 ETP |

---

## 12. Architecture cible

### Vue d'ensemble

```
                        ┌─────────────────────────────────────────────┐
   Clients              │  Web (MapLibre/deck.gl)  ·  Mobile offline  │
                        │  QGIS / DuckDB / notebooks  ·  Agents (MCP) │
                        └───────────────┬─────────────────────────────┘
                                        │ HTTPS (OGC API, REST, MCP, SSE)
                        ┌───────────────▼─────────────────────────────┐
                        │            REVERSE PROXY / CDN              │
                        │   (tuiles PMTiles/COG servies du S3 direct) │
                        └───────┬───────────────────────┬─────────────┘
                                │                       │ HTTP Range
        ┌───────────────────────▼───────────┐   ┌───────▼──────────────┐
        │        CŒUR (monolithe modulaire) │   │   OBJECT STORAGE S3  │
        │  · catalogue & métadonnées (STAC) │   │  GeoParquet/Iceberg  │
        │  · identité & politiques (ReBAC)  │   │  COG · PMTiles       │
        │  · OGC API Features/Tiles/Styles  │   │  pièces jointes      │
        │  · builder & AppConfigs           │   └───────▲──────────────┘
        │  · alertes & partage              │           │ écrit
        │  · serveur MCP · recherche hybride│   ┌───────┴──────────────┐
        └───────┬───────────────┬───────────┘   │  WORKERS (jobs)      │
                │               │ file de jobs  │  import/ETL · tuiles │
        ┌───────▼─────────┐     └──────────────▶│  analyses · IA batch │
        │ POSTGRES/POSTGIS│                     └──────────────────────┘
        │ + pgvector      │──CDC──▶ lakehouse
        │ (chaud, RLS)    │        ┌──────────────────────┐
        └───────▲─────────┘        │ STREAMING (option)   │
                │ ingestion        │ NATS · géofencing    │──▶ SSE clients
                └──────────────────│ fenêtres · alertes   │──▶ lakehouse
                     MQTT/HTTP     └──────────────────────┘
```

### Composants principaux et technologies recommandées

| Composant | Technologie | Justification |
|---|---|---|
| Cœur | Monolithe modulaire (Go ou TypeScript/Node — choix d'équipe), OpenAPI | Un artefact, frontières de modules outillées |
| Base chaude | PostgreSQL + PostGIS + pgvector | Standard de fait, RLS, CDC |
| Stockage froid | S3-compatible (MinIO on-prem) | Cloud-agnostique |
| Formats | GeoParquet, Iceberg (option), COG, PMTiles, FlatGeobuf, Zarr | Cloud-native, « le format est l'API » |
| Catalogue | STAC + DCAT | Interop imagerie ET open data |
| Tuiles dynamiques | Martin | MVT depuis PostGIS, léger (Rust) |
| Génération tuiles | Planetiler / Tippecanoe (workers) | Éprouvés |
| Rendu client | MapLibre GL JS + deck.gl, CesiumJS en option 3D lourde | Ouverts, GPU |
| Impression | QGIS Server headless | Meilleur rendu print open source |
| Analytique | DuckDB (serveur + WASM navigateur) | OLAP embarqué sur GeoParquet |
| Identité | Keycloak (OIDC) | Fédération entreprise, souveraineté |
| Autorisation | OpenFGA (ou moteur embarqué compatible) + RLS PostGIS | ReBAC partage + sécurité donnée |
| Streaming | NATS JetStream (option), Kafka en référence | Proportionné |
| Jobs | File Postgres (SKIP LOCKED) ou NATS, workers conteneurisés | Pas de dépendance de plus |
| IA | Serveur MCP natif ; LLM enfichable (API Claude/compatibles, vLLM local) | Souveraineté, pas de lock-in modèle |
| Observabilité | OpenTelemetry → Grafana/Loki/Tempo (référence) | Standard |
| Déploiement | Images OCI, Docker Compose (Solo/Standard), Helm (Scale) | Continuum sans migration |

### Flux de données types

1. **Publication** : dépôt d'un fichier (ou référencement d'une table PostGIS / d'un
   bucket) → worker : validation, conversion GeoParquet + PMTiles, extraction de
   métadonnées + embeddings → item STAC catalogué → servable immédiatement (OGC API +
   tuiles). *Aucune étape « créer un service ».*
2. **Consultation** : le client charge une AppConfig → MapLibre lit les PMTiles
   directement du CDN/S3 (le cœur n'est pas dans le chemin des tuiles statiques) →
   les données chaudes passent par OGC API Features/Martin avec RLS appliquée.
3. **Édition terrain** : mobile offline (GeoPackage local) → synchro différée →
   PostGIS → CDC → lakehouse à jour en minutes → dashboards analytiques frais.
4. **Temps réel** : capteurs MQTT → (NATS) → géofencing/règles → alertes multicanal +
   couche live SSE → archivage GeoParquet en continu.
5. **Agentique** : agent (interne ou client MCP externe) → mêmes APIs, permissions de
   l'utilisateur, chaque action auditée → produit requêtes, cartes, configs
   *inspectables*.

### Expérience utilisateur

- **Temps-vers-la-première-carte < 5 minutes** : je dépose un fichier, j'obtiens une
  carte stylée correctement (classification et palette proposées par IA, vérifiables),
  partageable par lien.
- Un seul environnement : catalogue → carte → app/dashboard → partage, sans changer
  de produit ; le langage naturel disponible partout comme accélérateur, jamais comme
  passage obligé.
- Le terrain est un mode, pas une app à part : la même app configurée fonctionne
  offline.

### Expérience développeur

- `docker compose up` → plateforme complète locale en 5 minutes, données de démo
  incluses.
- **La config est l'API** : tout objet (app, style, politique, alerte) est un document
  JSON schématisé — versionnable en Git, générable par IA, applicable par CLI/CI.
- SDK Web Components + client TypeScript généré (OpenAPI) ; plugins = modules ES avec
  manifeste de permissions ; marketplace signée pour distribuer.
- Serveur MCP : le développeur peut scripter la plateforme *en parlant à son agent*.

### Trajectoire 5 ans (esquisse)

1. **An 1** — cœur + données (PostGIS/S3/STAC) + carto (MapLibre/PMTiles/OGC API) +
   partage : la boucle publier→cartographier→partager, imbattable en simplicité.
2. **An 2** — builder config-driven + SDK + recherche sémantique + copilot
   utilisateur ; profil Solo/edge.
3. **An 3** — lakehouse complet (Iceberg, DuckDB-WASM), temps réel palier 1,
   offline-first terrain.
4. **An 4** — marketplace, multi-tenant commercial, copilotes admin/dev, ABAC spatial
   avancé.
5. **An 5** — profondeur analytique (Processes, imagerie/Zarr), écosystème tiers
   autoporteur.

Le pari d'ensemble : ArcGIS Enterprise est imbattable sur la largeur du catalogue à
horizon 5 ans — donc on ne joue pas ce match. On joue **simplicité d'adoption,
ouverture radicale des formats, intégration à la data platform, et architecture
AI-native** : quatre terrains où une feuille blanche 2026 bat structurellement vingt
ans d'héritage.
