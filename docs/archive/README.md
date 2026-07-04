# Archives — études préalables (générations G1/G2)

Ces documents sont **l'histoire du projet, pas sa référence**. Ils datent d'avant
la décision d'orientation du 2026-07-04 (option C) et décrivent des stratégies
abandonnées ou dépassées. Ils sont conservés pour la traçabilité des choix.

| Document | Génération | Ce qu'il décrivait | Pourquoi archivé |
|---|---|---|---|
| `synthese.md`, `stacks-comparatif.md`, `stacks-production.md`, `stack3-modern-web-gis.md` | G1 — « la stack » | Assemblage de briques FOSS4G (GeoNode, GeoServer, Superset, Airflow, Kafka…) pour égaler ArcGIS Enterprise | L'assemblage n'est pas un produit ; contredit la vision (empreinte, Kafka par défaut) |
| `IMPLEMENTATION_PLAN.md` | G1 | Plan en 8 phases de déploiement de la stack | Remplacé par la feuille de route option C |
| `plateforme-modulaire.md` | G2 — « OGE/GeoCore » | Produit à noyau + modules (microservices), parité ArcGIS 11.4 | Objectif de parité abandonné ; le monolithe modulaire lui est préféré |

**Les documents de référence actuels** sont dans [`../vision/`](../vision/) :

1. [`2026-07-04-feuille-de-route-geostudio.md`](../vision/2026-07-04-feuille-de-route-geostudio.md) — **l'autorité** : phasage SP-1→SP-9, arbitrages tranchés
2. [`2026-07-04-comparatif-projet-actuel-vs-vision.md`](../vision/2026-07-04-comparatif-projet-actuel-vs-vision.md) — la décision d'orientation (option C) et ses raisons
3. [`2026-07-04-plateforme-webgis-nouvelle-generation.md`](../vision/2026-07-04-plateforme-webgis-nouvelle-generation.md) — la vision long terme
