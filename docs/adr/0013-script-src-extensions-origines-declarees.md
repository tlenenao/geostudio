# 0013 — `script-src` : origines des extensions déclarées, calculées depuis la table `extensions`

Statut: acceptée
Source : spec `docs/superpowers/specs/2026-10-04-cloture-backlog-38-rev-design.md` (arbitrage 166, QCM 2026-10-04) ; spec SP-48 §4 (blocage 3, Option A) ; REV-166, GAP-72.

## Contexte

SP-48 a basculé la CSP en enforcing pour `img-src`/`connect-src` (allowlist calculée et poussée à Traefik). Les widgets d'extension tiers (SP-8, chargement ES dynamique depuis `Extension.module_url`) exigent que `script-src` admette leur origine. Une extension est un code exécuté avec les droits DOM du shell : l'ouvrir est une décision de sécurité.

`CLAUDE.md` et `GAP-72` affirmaient « `script-src` toujours `'self'` en dur » ; le code disait déjà le contraire (commit `1e9375dc`, Option A tranchée par Tanguy le 2026-09-06). Cet ADR consigne l'état réel.

## Décision

`script-src` vaut `'self'` plus l'origine (schéma + hôte + port) de chaque ligne **activée** de la table `extensions` (`compute_csp_allowlist`, `core/app/security/service.py` ; rendu par `core/app/security/traefik_render.py`). La table existante est la source de vérité : **pas de modèle `ExtensionOrigin` dédié** (déviation par rapport au libellé de l'arbitrage 166, la table `extensions` portant déjà `tenant_id`, `owner_id`, `enabled` et la garde `admin.extensions.manage`). Une extension désactivée (`enabled = false`, commit `f8dbfacd`) n'élargit rien. Sans extension déclarée, `script-src 'self'` est inchangé. Jamais de `'unsafe-inline'`, `'unsafe-eval'` ni de joker.

## Conséquences

- L'écriture est gardée par `Privilege.ADMIN_EXTENSIONS_MANAGE` ; l'allowlist protège contre une origine non déclarée, **pas** contre un fichier substitué sur une origine déclarée (confiance à la granularité de l'hôte, pas du contenu).
- La requête de calcul ne filtre pas par tenant : la CSP est globale au routeur Traefik, donc l'union des origines de tous les tenants s'applique au shell de tous. **Limite assumée** : l'isolation par tenant porte sur la déclaration, pas sur l'exécution (une CSP par tenant exigerait un routage par domaine de tenant, hors périmètre). Un opérateur multi-tenant à fort cloisonnement ne doit pas déléguer `admin.extensions.manage` à un tenant non maîtrisé.
- Le schéma `http` est accepté par `_origin` (pas d'exigence `https` côté CSP) ; l'exigence de transport relève de la configuration de l'opérateur. Durcir (https obligatoire hors développement, SRI sur les modules, CSP par domaine de tenant) demande un nouvel ADR qui remplace celui-ci.
