# c04 — Qualité du shell (code)

Couvert : any/casts (2 `any` hors tests, 16 `as unknown as`), toFrontLayer vs schéma cœur, fetch nus hors ItemClient, composants >500 lignes, eslint-disable exhaustive-deps, code mort (tsc --noUnusedLocals/Parameters : propre).
Non couvert : analyse fine des hooks instables et fuites d'effets hors MapView/LayersPanel ; duplication fine (pas de jscpd) ; DesktopItemClient (554 l.) non relu.
Méthode : lecture directe + grep + wc + tsc. Aucune exécution de test (findings verified = commandes de lecture).
Commandes : grep fetch/any/as unknown/eslint-disable, find|wc -l, npx tsc --noEmit --noUnusedLocals --noUnusedParameters.
