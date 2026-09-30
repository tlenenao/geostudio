# c05 - Qualité des tests

Couvert : skips silencieux postgis (exécuté), assertions de durée (perf import, copilote), sleeps E2E, handler générique mocks.ts, coverage.xml local.
Non couvert : suite pytest complète et vitest (pas de base postgis, CORE_TEST_DATABASE_URL vide ; pas de run E2E complet) ; flakiness réelle non mesurée (aucun rejeu répété) ; couverture shell détaillée.
Écartés : test_copilot_routes.py:708 (latence LLM 3 s contre budget 0,2 s, la marge prouve la propriété) ; test_collections_spatial_index (0028 sans upgrade/downgrade réels) déjà connu (audit pré-release item 6).
Méthode : lecture de code, analyse de core/coverage.xml, un run pytest ciblé.
Commandes : pytest 3 fichiers avec CORE_TEST_DATABASE_URL vide (1 passed, 6 skipped) ; grep waitForTimeout/pytest.skip/elapsed ; analyse XML.
