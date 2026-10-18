# ADR 0029 — Collecte de terrain hors-ligne : file locale idempotente et PWA en liste blanche

Statut: acceptée

Source : spec `docs/superpowers/specs/2026-10-18-l8-collecte-terrain-offline-design.md`
(lot L8, AUD-004/070/071) ; ADR 0017 (soumission publique modérée).

## Contexte

Un agent de terrain sans réseau doit pouvoir saisir (champs + photos), fermer
l'application, la rouvrir, et retrouver ses saisies envoyées une seule fois au
retour du réseau. Deux surfaces : l'app connectée (`/apps/:pk`) et la page
publique `/collect/:token` (ARC-10). Le cœur ne doit ni créer de doublon sur
rejeu, ni laisser un service worker intercepter du trafic d'API ou d'identité.

## Décision

1. **File locale dans IndexedDB** (`gs-collect-v1`), une file par propriétaire
   (`<tenant>:<utilisateur>` ou `public:<token>`) : une saisie d'Alice n'est
   jamais rejouée sous l'identité de Bob.
2. **Idempotence de bout en bout** : l'identifiant de saisie (`opId`) est
   l'`Idempotency-Key` (UUID) de `POST items` et de la confirmation de pièce
   jointe, `clientOpId` côté soumission publique ; l'horodatage d'origine
   voyage dans `X-GS-Offline-Created-At`. Un rejeu après réponse perdue
   retrouve la même ressource (migrations 0160–0163).
3. **Kit de collecte** (`GET /v1/collections/{id}/collect-kit`,
   `GET /v1/public/submit/{token}/kit`) : schéma + domaines nécessaires au
   formulaire, mis en cache pour la saisie hors-ligne ; même masquage GAP-22 que
   les autres chemins de lecture.
4. **Soumission publique** : preuve de travail (hashcash, `GET .../challenge`)
   exigée par défaut, résolue côté client par tranches sur le fil principal.
5. **Service worker en liste blanche** : navigations `/`, `/collect/*`,
   `/apps/*` (réseau d'abord, repli sur `/index.html`) et `/assets/*`
   (cache d'abord, précache du graphe statique + `CollectPage` + moteur de
   file). Jamais d'API, de `/mcp`, d'`/embed`, de requête avec `Authorization`
   ni d'autre origine. Mise à jour proposée par bannière, jamais imposée.
6. **Pas de Background Sync** (non retenu, YAGNI) : Chromium seul, et le SW
   devrait lire IndexedDB et porter un jeton. La synchro part à l'ouverture, au
   retour du réseau (`online`), sur minuteur avec recul, et à la demande.

## Conséquences

- Une app privée n'est rouvrable hors-ligne qu'après un chargement en ligne
  antérieur sous contrôle du SW, et sa configuration n'est pas mise en cache :
  seuls la file et la bannière sont garanties ; le formulaire complet hors-ligne
  est offert par la page publique (kit en cache).
- Plafonds locaux : 100 saisies, 200 Mo de pièces par propriétaire.
- La soumission publique sans preuve de travail est refusée (rupture pour les
  clients tiers ARC-10 : à annoncer dans `CHANGELOG.md`).
- Le registre de preuves de travail utilisées est par processus (limite
  assumée tant que le cœur tourne en un processus ; voir le runbook).
- `/sw.js` n'est jamais mis en cache (`no-cache`, nginx) et reste couvert par
  la CSP existante (`worker-src 'self'`).
