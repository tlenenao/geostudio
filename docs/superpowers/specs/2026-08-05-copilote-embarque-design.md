# Copilote IA embarqué dans le builder (SP-20)

> Spec issue du brainstorm du 2026-08-05. Identifié comme gap **G8** (priorité
> stratégique P0) dans `docs/vision/geostudio-dataviz-analytics-gap-analysis.md`
> §4.3/§7.10 le 2026-07-14, jamais transformé en spec jusqu'ici. Inscrit comme
> **SP-20** dans la feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md`). **Dépend de SP-19**
> (undo/redo général du builder, découvert comme prérequis pendant ce
> brainstorm) ; sinon indépendant de tout autre SP — les outils MCP qu'il
> orchestre existent déjà (SP-2/SP-7/SP-14l).

## 1. Contexte & motivation

Le MCP (SP-2, SP-7, étendu en SP-14l) rend GeoStudio opérable par un agent
**externe** — Claude Desktop ou tout autre client MCP standard peut lister les
items, lire/écrire une config, chercher dans le catalogue, interroger un
dataset. C'est un différenciateur réel (aucun concurrent du benchmark
2026-07-09 n'a d'équivalent natif). Mais rien dans le shell lui-même ne permet
à un utilisateur du builder de taper « ajoute un indicateur du nombre
d'incidents ouverts » et de voir le widget apparaître : l'IA est opérable de
l'extérieur, invisible de l'intérieur. C'est le seul point du gap-analysis
2026-07-14 qui pointe vers une brique **sans équivalent** dans la feuille de
route existante (les cinq autres — dataviz, analytics, BI, portails, 3D —
sont couverts par SP-11/12/13/14/17).

**Cadrage volontairement étroit pour la v1** : le copilote propose des
**micro-actions sur la config en cours d'édition** (ajouter un widget,
référencer un dataset, expliquer une donnée, créer un item ciblé) — jamais une
génération opaque de dashboard complet à l'aveugle. Le risque produit central
est la confiance : un copilote qui édite fidèlement, pas par pas, la config
affichée, vaut mieux qu'un générateur qui produit un résultat que l'auteur ne
comprend pas.

## 2. Architecture

Trois surfaces séparées, pour ne jamais créer de capacité que le MCP externe
n'aurait pas déjà :

```
┌─────────────────────────────── SHELL (navigateur) ────────────────────────────────┐
│  CopilotPanel (nouvel onglet du builder, aux côtés de PropsPanel/ActionsPanel/…)    │
│    │                                                                                │
│    │ 1. signinSilent() vers Keycloak (resource=CORE_MCP_AUDIENCE), au premier tour  │
│    │    → token MCP gardé en mémoire JS uniquement (jamais localStorage)            │
│    │                                                                                │
│    │ 2. POST /copilot/turn { message, history, mcpToken, currentConfig, itemId }    │
│    ▼                                                                                │
└────┼────────────────────────────────────────────────────────────────────────────────┘
     │ (token REST normal du shell)
     ▼
┌─────────────────────────────── CŒUR — module copilot/ ─────────────────────────────┐
│  routes.py  POST /copilot/turn                                                      │
│    ├─ LLMProvider.chat(messages, tools)     CORE_LLM_PROVIDER=openai|fake           │
│    │     tools = outils MCP (allowlist)  +  outils client (schémas générés)         │
│    ├─ tool_call MCP  → mcp_loopback.call(tool, args, bearer=mcpToken)               │
│    │     → JSON-RPC vers /mcp (même serveur, même chemin qu'un agent externe,       │
│    │        actor_kind=agent, audit_log déjà tracé par mcp/tools.py)                │
│    │     → boucle jusqu'à 6 itérations, puis réponse finale ou repli                │
│    └─ tool_call client → jamais exécuté côté serveur, renvoyé tel quel au shell     │
└──────────────────────────────────────────────────────────────────────────────────────┘
     │ { reply, clientOps }
     ▼
┌─────────────────────────────── SHELL ──────────────────────────────────────────────┐
│  CopilotPanel applique clientOps via applyClientOp.ts (mêmes fonctions pures que    │
│  la palette/PropsPanel) → canvas mis à jour immédiatement, annulable via l'undo     │
│  général (SP-19), rien n'est sauvegardé avant le clic « Enregistrer » existant      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Pont d'audience MCP

Les tokens MCP utilisent une audience distincte (`CORE_MCP_AUDIENCE`) du token
REST du shell (`mcp/auth.py`, `KeycloakTokenVerifier`) — frontière de sécurité
délibérée de SP-2. Le shell complète donc le même flux OAuth 2.1+PKCE qu'un
client MCP externe, mais en silencieux via la session Keycloak SSO déjà
active (`signinSilent`, `oidc-client-ts`, déjà en dépendance) — pas de nouvel
écran de login, pas de nouveau client Keycloak au-delà d'une redirect URI
silencieuse autorisée pour l'origine du shell. Le token MCP obtenu ne quitte
jamais le navigateur autrement que dans le corps de la requête
`POST /copilot/turn`, n'est jamais persisté côté serveur au-delà de cette
requête, jamais en `localStorage` côté client.

## 3. Composants

### Cœur — module `copilot/`

- **`llm_provider.py`** — `Protocol LLMProvider.chat(messages, tools) -> LLMTurn`
  (texte assistant + tool_calls). Même convention que `EmbeddingProvider`
  (SP-7, `search/providers.py`) : `FakeLLMProvider` scriptable (réponses
  déterministes pilotées par le contenu du prompt, pour les tests et le mode
  `CORE_AUTH_MODE=mock`) et `OpenAICompatibleLLMProvider`
  (`CORE_LLM_PROVIDER=openai`, `CORE_LLM_API_URL`, `CORE_LLM_API_KEY`,
  `CORE_LLM_MODEL`) — format chat completions + tool calling standard,
  compatible OpenAI et la plupart des passerelles/modèles locaux
  (vLLM, Ollama, LM Studio).
- **`mcp_loopback.py`** — client qui appelle `POST /mcp` en JSON-RPC avec le
  token MCP transmis (`Authorization: Bearer <mcpToken>`). Aucune logique
  d'outil dupliquée : c'est un vrai appel réseau au serveur MCP existant.
- **`tools_allowlist.py`** — liste fermée des outils MCP exposés au copilote :
  `search_catalog`, `list_items`, `explain_dataset`, `run_analytics_query`,
  `create_item`, `create_form_app`. **Jamais** `save_app_config`, **jamais**
  `set_sharing` — le copilote ne modifie jamais un item existant en base
  directement ; il peut en créer un nouveau (via les mêmes outils qu'un agent
  MCP externe) mais l'édition de l'item déjà ouvert dans le builder reste
  cantonnée aux opérations client (§3, shell). Un `tool_call` du LLM vers un
  outil hors de cette liste est rejeté côté serveur avant tout appel MCP,
  même si le modèle insiste.
- **`routes.py`** — `POST /copilot/turn`. Boucle : tant que la réponse du LLM
  contient des `tool_calls` MCP, on les exécute via `mcp_loopback` et on
  réinjecte le résultat (ou l'erreur — une `ValueError` d'un outil MCP,
  ex. « item not found », est réinjectée comme résultat d'outil, pas avalée
  silencieusement) ; **6 itérations maximum**, timeout global ~30 s. Dès que
  la réponse contient un ou plusieurs `tool_calls` **client**, la boucle
  s'arrête et l'ensemble `{ reply, clientOps }` est renvoyé — une opération
  client ne produit jamais de résultat réinjecté au LLM dans le même tour.
- **`GET /instance`** (existant, `app/instance/routes.py`) gagne un champ
  `copilotEnabled: bool`, miroir de `readOnly` — vrai seulement si
  `CORE_LLM_PROVIDER` est configuré.

### Shell — `shell/src/builder/copilot/`

- **`CopilotPanel.tsx`** — nouvel onglet du sélecteur de panneaux du builder
  (aux côtés de Props/Actions/Données/Thème/Variables/Navigation), visible
  seulement en mode édition (pas preview/runtime) et seulement si
  `copilotEnabled` (sinon l'onglet n'existe pas). Historique affiché,
  éphémère (perdu au rechargement, aucune persistance en v1), champ de
  saisie, résumé textuel des `clientOps` appliquées sur chaque réponse, bouton
  « Annuler » qui appelle `undo()` du `UndoContext` (SP-19).
- **`useMcpToken.ts`** — hook `signinSilent()` décrit en §2.1.
- **`clientTools.ts`** — schémas des opérations client
  (`addWidget`, `updateWidgetProps`, `removeWidget`, `addDataSource`,
  `setFilter`) **générés depuis `registry.ts`** (types de widgets et leurs
  props déjà déclarées pour le `PropsPanel` généré) plutôt que maintenus à la
  main — un nouveau widget ajouté au registre devient automatiquement
  éditable par le copilote sans code copilote supplémentaire.
- **`applyClientOp.ts`** — exécute une `ClientOp` en réutilisant les fonctions
  pures existantes du builder (`setPageLayout`, `nextFreePosition`, etc. de
  `grid.ts`/`pages.ts`) — le chemin qu'emprunte déjà un clic dans la palette
  ou le `PropsPanel`, donc chaque opération traverse le point de commit unique
  de l'undo (SP-19) et bénéficie de la même validation que l'UI manuelle.

### Contexte envoyé à chaque tour

L'historique complet des messages visibles (dont les résultats d'outils MCP,
pour la mémoire inter-tours — ex. « le dataset trouvé au tour précédent »),
la config actuelle sérialisée (recalculée à chaque tour depuis l'état live du
builder, capte les éditions manuelles faites entre deux prompts), et
l'identité de l'item ouvert (id, type, titre).

## 4. Sécurité

Aucun nouveau chemin d'autorisation :

- Chaque appel MCP passe par `can()`/`audit_log` exactement comme un agent
  MCP externe (`actor_kind=agent`, déjà tracé par `mcp/tools.py`).
- Les opérations client ne touchent jamais la base avant le clic
  « Enregistrer » existant (déjà audité par le flux normal de
  `save_app_config` REST).
- Mode démo lecture seule (`is_read_only_mode()`) bloque déjà `create_item`/
  `create_form_app` côté MCP — le copilote en hérite gratuitement : recherche
  et explication fonctionnent, la création est refusée, sans code spécifique
  nouveau.
- Le token MCP ne quitte jamais le navigateur autrement que dans le corps de
  la requête `/copilot/turn` ; jamais persisté côté serveur, jamais en
  `localStorage`.

## 5. Gouvernance & coûts

- **Off par défaut.** Sans `CORE_LLM_PROVIDER` configuré, `copilotEnabled`
  est faux et le panneau n'existe pas dans le shell — un admin self-hosted
  doit consciemment brancher une clé pour l'activer.
- **Pas de quota par utilisateur/tenant en v1** (déféré, risque documenté
  §7) : un admin qui active une clé paie l'usage de toute l'instance sans
  plafond.

## 6. Hors périmètre v1

- Historique de conversation persistant (au-delà de la session du navigateur).
- Quotas/limites de coût par tenant ou utilisateur.
- Génération de dashboard complet depuis un seul prompt — le copilote reste
  des micro-actions + création ciblée d'un item (`create_item`/
  `create_form_app`), jamais un générateur de config globale à l'aveugle.
- Copilote en mode preview/runtime pour les utilisateurs finaux — réservé à
  l'auteur en édition dans le builder.
- Second fournisseur LLM (API native Anthropic) — le `Protocol
  LLMProvider` le permet plus tard sans réécriture, non fait en v1.
- Usage libre du rôle analyste/SQL Lab au-delà de `run_analytics_query` déjà
  listé dans l'allowlist.

## 7. Risques

- **Coût LLM incontrôlé** (pas de quota v1) — assumé et documenté, à
  réévaluer si un abus réel survient sur une instance publique.
- **Hallucination d'arguments d'outil** malgré des schémas stricts — mitigé
  par la validation serveur déjà en place (schémas Pydantic sur chaque outil
  MCP) et la validation côté client (mêmes fonctions que l'UI manuelle,
  §3 `applyClientOp.ts`).
- **Latence perçue** si la boucle MCP interne itère plusieurs fois avant de
  répondre — pas de garde-fou UX au-delà d'un simple indicateur de
  chargement en v1.
- **Dépendance dure à SP-19** : sans undo/redo général, une suggestion
  malvenue du copilote n'est réversible qu'à la main — ce chantier ne
  démarre pas avant que SP-19 soit livré (ou en tout début d'exécution
  conjointe, à trancher au moment du plan).

## 8. Tests & critères d'acceptation

- **Cœur** : `llm_provider.py` (`FakeLLMProvider` scriptée), `mcp_loopback.py`
  (mock HTTP vers `/mcp`), boucle de `routes.py` (garde-fou 6 itérations,
  rejet d'un outil hors allowlist même si le LLM le demande), `GET /instance`
  reflète `copilotEnabled` selon `CORE_LLM_PROVIDER`.
- **Shell** : `CopilotPanel` (envoi de message, application des `clientOps`,
  bouton Annuler), `useMcpToken` (mock `signinSilent`), génération des
  schémas d'outils client depuis `registry.ts`.
- **E2E (Playwright, mode mock)** : panneau absent sans provider configuré ;
  prompt d'explication (lecture seule, aucun changement de config) ; prompt
  d'ajout de widget (canvas mis à jour, annulable via SP-19, puis sauvegarde
  par le chemin normal) ; utilisateur lecture-seule peut interroger mais pas
  créer.

**Critères d'acceptation** :
1. Sans `CORE_LLM_PROVIDER`, aucun bouton copilote visible.
2. « Explique ce dataset » appelle `explain_dataset` en loopback MCP (audité
   `actor_kind=agent`), répond en langage naturel, ne modifie rien.
3. « Ajoute un indicateur du nombre d'incidents ouverts » fait apparaître le
   widget sur le canvas avant tout enregistrement, annulable via l'undo
   général (SP-19), puis sauvegardable normalement.
4. En mode démo lecture seule, la création est refusée (hérité de
   `is_read_only_mode`), la recherche/explication fonctionne.
5. Un outil hors allowlist demandé par le LLM est rejeté côté serveur, jamais
   exécuté.
6. Dépassement du plafond d'itérations produit un message de repli, pas de
   crash ni de boucle infinie.
