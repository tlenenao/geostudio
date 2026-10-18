# Runbook — collecte de terrain hors-ligne (L8)

Pour l'exploitation et le support : ce qui est stocké sur l'appareil, comment
diagnostiquer une saisie « bloquée », et ce que le service worker peut casser.
Décision : [ADR 0029](../adr/0029-collecte-terrain-hors-ligne.md).

## Ce qui vit sur l'appareil

| Où | Quoi | Effacé par |
|---|---|---|
| IndexedDB `gs-collect-v1` (`outbox`, `blobs`, `kits`) | saisies en attente, pièces jointes, kit de la collecte | envoi réussi (saisie), abandon dans l'écran, « Effacer les données du site » |
| Cache Storage `gs-shell-<build>` / `gs-assets-<build>` | coquille du shell et chunks | purge des anciens `gs-*` à l'activation d'un nouveau SW |
| `localStorage` `gs-collect-owner` | dernier propriétaire (rechargement hors-ligne) | déconnexion du navigateur |

Aucune réponse d'API n'est jamais mise en cache. Vider les données du site
**perd les saisies non envoyées** : l'écran « Saisies hors-ligne » propose
l'export JSON de chaque saisie avant abandon.

## Diagnostiquer une saisie qui ne part pas

1. Écran de la saisie (sous le formulaire) : l'état dit pourquoi.
   - « En attente d'envoi » + raison réseau : attendre ou « Synchroniser maintenant ».
   - « À corriger » : refus de validation (422), détail champ par champ ; corriger
     depuis la liste, la même clé est renvoyée.
   - Alerte « session expirée » : un 401 a suspendu la synchro, la file est intacte ;
     se reconnecter puis « Reprendre ».
2. Côté cœur : un second envoi de la même `Idempotency-Key` renvoie la
   ressource déjà créée avec l'en-tête `Idempotent-Replay: true` (jamais un
   doublon) ; 409 « operation in progress » = le premier envoi n'est pas fini,
   le client réessaie seul.
3. Soumission publique : 429 = budget du limiteur public (20/min, partagé avec le
   kit et le challenge) ; 400 « preuve de travail » = défi expiré ou déjà utilisé
   (le client en redemande un seul).

## Service worker

- Désactiver en urgence : retirer le bloc `location = /sw.js` ne suffit pas ;
  publier un `sw.js` qui se désenregistre (`self.registration.unregister()`) et
  vide les caches `gs-*`.
- Vérifier la fraîcheur : `curl -sI https://<hôte>/sw.js` doit montrer
  `Cache-Control: no-cache`. `test_shell_service_worker_is_never_cached_and_allowed_by_the_csp`
  garde cette propriété.
- Une nouvelle version est proposée par la bannière « mise à jour disponible » ;
  elle n'est appliquée qu'au clic (aucune perte de formulaire en cours).

## Limites connues

- Registre des preuves de travail utilisées : par processus du cœur. Avec
  plusieurs réplicas, un même défi peut être rejoué une fois par réplica
  (borné par le limiteur et l'idempotence `clientOpId`).
- Les règles `calculation` du formulaire ne sont pas évaluées côté client
  hors-ligne ; le kit public ne porte ni `visibleWhen` ni aide de champ.
- Pas de dessin de géométrie dans le formulaire, ni de code QR.
