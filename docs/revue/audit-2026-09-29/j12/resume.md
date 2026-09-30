# j12 — Terrain : mobile et tactile — résumé

## Périmètre couvert
- Seuils de viewport 360/768/899/900/1280 : bascule onglets + navigation basse (≤ 899 px) vs trois colonnes + barre de domaines (≥ 900 px).
- Chrome mobile à 360 px : en-tête, navigation basse, onglets triptyque, tiroir d'import avec fenêtre réduite à 300 px (clavier virtuel simulé), débordement horizontal, hauteur de page.
- Carte tactile réelle (Input.dispatchTouchEvent via CDP) : tap → popup, pincement, glissement, mesure distance, croquis rectangle, tracé libre, popup au bord de l'écran.
- Cibles tactiles (24 px WCAG 2.5.8, 44 px confort) sur le chrome, le popup, le canevas de l'éditeur d'app et le panneau Couches.
- Thèmes clair/sombre (axe : contraste + target-size sur 5 écrans à 360 px), prefers-reduced-motion (CSS des boutons et cadrage de carte, avec témoin sans réduction).
- Runtime d'app à 360 px (empilement sm), site public et fiche dataset publique à 360 px.
- 30 tests : 17 passent (régression), 13 fixme (j12-001 ×2, puis j12-002 à j12-012 ; j12-013 à j12-016 sont en code-read ou sans test dédié).

## Non couvert
- Rendu réel du fond de carte : les styles demotiles/cartocdn sont remplacés par un style vide local (`stubBasemap`) ; le worker MapLibre est servi avec un type MIME corrigé par `page.route` (contournement de j12-001) dans tous les tests de carte sauf les deux tests j12-001.
- Vrai clavier virtuel iOS/Android, Safari/WebKit, Firefox : seul Chromium émulé (hasTouch, CDP) ; pas de test de zoom système, de safe-area réelle ni de rotation d'appareil.
- Pointeur grossier (`pointer: coarse`) : non émulé hors `isMobile`, donc pas de test dédié du hint ⌘K (j12-013 en code-read).
- Capacités désactivées sur la stack (ETL, export, admin tools, quotas, LLM) : pipelines, rapports, copilote, quotas, extensions tierces non testés en mobile.
- Import de fichier : POST /v1/uploads et /alerts/{id}/evaluate répondent 500 (j03-001) ; les données viennent du seed j03 (boto3 + worker) et de j10 (SQL).
- Builder de pipeline (canevas DAG), SQL Lab, CodeMirror, formulaires de widgets : non audités en tactile.
- Drag & drop HTML5 du builder de formulaire (form.tsx `draggable`) : non testé au toucher (hypothèse : inopérant, non prouvée).

## Méthode
Sondes exploratoires jetables (mesure des boîtes, débordements, état MapLibre retrouvé par les hooks React de `.maplibregl-map`) puis specs figées. Chaque test fixme a été exécuté sans son marqueur et a échoué pour la raison attendue (valeurs relevées dans les findings). Cause racine de j12-001 établie en créant un `new Worker(..., {type:"module"})` vers l'URL réelle (erreur de chargement) et en constatant les tuiles en état `loading`, puis prouvée par le témoin où seul le Content-Type est corrigé.

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j12` (17 passed, 13 skipped)
- `cd shell && npx eslint e2e/journeys/j12 && npx prettier --check e2e/journeys/j12`
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j12 --repo-root ..`
