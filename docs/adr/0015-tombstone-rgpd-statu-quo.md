# 0015 — Tombstone d'effacement RGPD : statu quo, conditionnel à la validation du DPO

Statut: acceptée (conditionnelle : validation du DPO attendue, hors code)
Source : spec `docs/superpowers/specs/2026-10-04-cloture-backlog-38-rev-design.md` (arbitrage 272 a, QCM 2026-10-04) ; REV-272 (a) ; SP-58 (RGPD Art. 17).

## Contexte

Quand un compte est anonymisé (RGPD Art. 17), le `oidc_sub` de la ligne `users` devient `erased:` + sha256 du `sub` d'origine (`core/app/users/repository.py::erased_sub`). À la connexion suivante, `get_or_create_user` recalcule ce condensat : s'il trouve la ligne tombstone, il répond 403 « this account has been erased » au lieu de recréer le compte (test : `core/tests/test_compliance_service.py`). C'est un pseudonyme déterministe, non salé, pas une anonymisation irréversible : qui détient le `sub` d'origine (fournisseur d'identité, journaux Keycloak) peut recalculer le condensat. Le `sub` Keycloak étant un UUID aléatoire, un dictionnaire sur le seul condensat est impraticable.

## Décision

**Statu quo** : le tombstone actuel est conservé (condensat non salé, pas de colonne dédiée, pas de suppression de la ligne). Décision **conditionnelle** : elle suppose que le DPO de l'organisation déployante valide que (i) le condensat d'un identifiant opaque n'est pas une donnée à caractère personnel dès lors que le `sub` d'origine n'est plus détenu côté cœur, et (ii) l'interdiction de recréation est une finalité légitime. Tant que cette validation n'est pas consignée, REV-272 (a) n'est pas close côté conformité.

## Conséquences

- Aucun changement de code.
- Alternatives écartées : (1) sel secret d'instance (HMAC) : ré-identification impossible sans la clé, mais rompt la reconnaissance du compte après restauration ou rotation de clé et ajoute un secret à gérer ; (2) suppression de la ligne : permettrait la recréation silencieuse du compte, donc la perte de la garantie d'effacement effectif.
- L'effacement côté Keycloak (suppression du compte) est une opération distincte, à la charge de l'exploitant.
- Si le DPO refuse : basculer sur (1) ; les `erased:` existants, à sens unique, ne sont pas migrables et seraient re-salés à leur prochaine occurrence.
