# Lot L9 « IA gouvernée » — conception

Source : `docs/revue/audit-2026-10-16/99-synthese.md` §4 (AUD-102/103/104/105/106/149) et
`dimensions/d23.md` (D23-01 à D23-12). Prémisses revérifiées dans le code le 2026-10-19 (piège n°12) :
toutes les preuves de d23 tiennent (ligne à ligne : `routes.py`, `harness.py`, `query_generation.py`,
`llm_provider.py`).

## Périmètre et choix

| AUD | Constat | Réponse |
| --- | --- | --- |
| 102 | Confirmation d'écriture aveugle | `confirmToken` HMAC (user + nom + sha256(arguments) + exp 10 min) émis avec l'op `confirmWrite`, exigé par `confirmWrite` ; le shell affiche un résumé des arguments |
| 103 | Audit lacunaire | `turnId` propagé (`X-GeoStudio-Turn`) puis fusionné par `write_audit` dans **tout** audit écrit pendant l'appel d'outil ; `argsSha256` sur `copilot.turn`/`mcp.tool_call` ; `outcome=error` sur toute exception ; `get_llm_provider()` dans le `try` |
| 104 | Pas d'évaluation, SQL non validé | `generate_sql_query` : SELECT unique (AST DuckDB), tables ⊆ {collectionId}, 2 réparations avec l'erreur, `warnings` si pas de Parquet ; données fencées par nonce sur les 4 générateurs ; jeu d'évaluation `core/evals/copilot/` + commande rejouable |
| 105 | Pas d'annotations/prompts | annotations dérivées de `WRITE_TOOL_NAMES` dans `harness.tool()` ; 2 prompts ; parité : `list_pipeline_ops`, `get_config_history` (lecture) |
| 106 | Contexte 64 k, pas de suivi | table `llm_usage` (0170), `usage` lu sur la réponse fournisseur, quota tenant `CORE_LLM_DAILY_TOKENS` (429), route `GET /v1/copilot/usage`, `max_tokens`/`temperature=0` sur les générateurs, contexte résumé au-delà de 64 k au lieu du 422 |
| 149 | Un fournisseur, pas de BYO-model | table `tenant_llm_settings` (0170) : modèle, URL, clé chiffrée (AES-GCM du coffre) par tenant, `GET/PUT/DELETE /v1/copilot/llm-settings` ; repli sur l'environnement |

## Décisions prises par défaut (à valider)

1. Clé du jeton de confirmation = dérivation HMAC de `CORE_SECRETS_MASTER_KEY` (déjà obligatoire),
   pas de nouvelle variable. Durée de vie 10 min, liée à l'utilisateur.
2. `turnId` = étiquette d'audit transmise par en-tête, comme `X-GeoStudio-Origin` : non frontière de sécurité.
3. Quota LLM : jetons/jour/tenant, `CORE_LLM_DAILY_TOKENS` vide = illimité (comportement actuel) ;
   un tour n'est refusé qu'avant l'appel (dépassement possible d'un tour). Pas de quota par utilisateur.
4. BYO-model (D4 « instance dédiée d'abord ») = surcharge **par tenant** du seul fournisseur
   OpenAI-compatible (modèle, URL, clé) ; pas de second fournisseur natif (Anthropic/Mistral passent par
   leur endpoint compatible). Privilège `settings.instance.manage`. L'URL reste filtrée par la garde d'egress.
5. Évaluation : cas hors ligne exécutés avec un fournisseur scripté (valident les validateurs, plancher
   100 % en CI) ; mode `--live` si `CORE_LLM_*` fourni (score imprimé, jamais bloquant en CI). Jeu de
   ~30 cas, pas 50 : extensible, format JSONL.
6. Parité MCP : seulement deux outils de lecture ajoutés ; écriture de features, collections, rollback,
   `delete_item` restent hors périmètre (chaque écriture exige sa confirmation copilote) — AUD-105 partiel.
7. Ressource `geostudio://catalog/{id}` non ajoutée (nécessite un contexte d'authentification de ressource) — partiel.
8. Le résumé de contexte (D23-06) est une troncature structurée (pages/widgets `{id,type,title}`), sans
   outils client de lecture à la demande — AUD-106 reste fermé sur le plafond, partiel sur l'ergonomie.
9. Hors périmètre : streaming SSE, opérations client supplémentaires (D23-12), `expectedVersion` obligatoire (D23-09).

## Jumelles de garde

Toute garde posée sur `/copilot/turn` l'est aussi sur : les 4 générateurs MCP (appel LLM direct, donc quota
+ usage + fencing), `confirmWrite`, l'audit `mcp.tool_call`. La route REST `POST /v1/analytics/sql`
n'appelle pas de LLM (rien à reporter).
