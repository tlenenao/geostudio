# Procédures manuelles de rejeu (REV-284 d, REV-286 c) — 2026-10-04

Ces deux lettres ne s'automatisent pas : elles exigent du matériel/logiciel réel.
Exécutant : <nom> — date : <AAAA-MM-JJ> — build (SHA de dev) : <sha>.
Non exécutées = les deux lettres restent `externe` sur leur REV (jamais fermées par défaut).

## A. Appareil tactile réel (REV-286 c)
Matériel : un téléphone ou une tablette réels (iOS Safari ou Android Chrome), pas l'émulation.
Stack : `https://<DOMAIN>` (profil prod) ou `http://<IP-hôte>:8300` sur le même réseau, auth OIDC.
1. Ouvrir une carte avec au moins 2 couches ; pincer-zoomer, déplacer : la carte répond, la page ne défile pas derrière.
2. Activer l'outil de croquis (tracé libre). Tracer au doigt une ligne de 3 s : un trait se dessine, la page ne défile pas (`touch-action: none`).
3. Tracer, puis poser un 2e doigt / glisser hors de l'écran (touchcancel) : le tracé partiel est ABANDONNÉ (REV-286 e), pas validé.
4. Toucher une entité : le popup s'ouvre, reste dans l'écran ; pivoter l'appareil : le popup se recale (REV-286 d).
5. Largeur 640-899 px (tablette portrait) : mode 2 volets (lot C) lisible, aucun clipping horizontal.
Relevé : pour chaque étape OK / KO + capture d'écran jointe (chemin) + remarque.

## B. Lecteur d'écran réel (REV-284 d)
Logiciel : NVDA + Firefox (Windows) ou VoiceOver + Safari (macOS). Cible : build courant, auth OIDC.
1. Catalogue : après une recherche, une seule annonce du nombre de résultats (pas de double annonce région sr-only + compteur visible).
2. Naviguer par titres (H) : `h1` page, `h2` « Résultats » avant la grille, `h3` des cartes ; sur `/public`, une embed et un site publié : un `h1` annoncé.
3. Formulaire avec erreur : le résumé d'erreurs est annoncé et le focus tombe sur le 1er champ invalide (lot C, REV-223).
4. Menu Actions (Radix) : ouverture/fermeture annoncées, focus restitué au déclencheur.
5. Dialogue de suppression (`alertdialog`) : intitulé et description annoncés à l'ouverture.
Relevé : OK / KO + transcription du lecteur (copier le texte annoncé) + remarque.
