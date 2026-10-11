# Procédures manuelles de rejeu (REV-284 d, REV-286 c) — 2026-10-04

Ces deux lettres ne s'automatisent pas : elles exigent du matériel/logiciel réel.
Exécutant : <nom> — date : <AAAA-MM-JJ> — build (SHA de dev) : <sha>.
Non exécutées = les deux lettres restent `externe` sur leur REV (jamais fermées par défaut).

## Prérequis communs

- Stack levée : `docker compose up -d` (`.env` complété, cf. `.env.example`), les 12 services `healthy` (`docker compose ps`).
- Build testé : `git rev-parse --short HEAD` (à reporter ci-dessus).
- URL de base, notée `<BASE>` ci-dessous : `https://<DOMAIN>` (profil prod, `DOMAIN` du `.env`) ou `http://<IP-hôte>:8300` (port du service `shell`, `docker-compose.yml`). IP hôte WSL2/Windows : l'appareil doit joindre cette IP sur le même réseau (pare-feu Windows : autoriser le port 8300 en entrée).
- Compte : realm Keycloak `geostudio` du dépôt (`deploy/keycloak/geostudio-realm.json`) : `alice` / `Demo1234!` (ou `bob` / `Demo1234!`). Ces comptes de démo n'existent que si le realm importé est celui du dépôt ; en prod, utiliser un compte réel avec rôle Créateur ou Administrateur (le croquis et l'édition de carte l'exigent). Se connecter via le bouton de connexion du shell (redirection Keycloak).
- Données : une carte `<BASE>/maps/<pk>` contenant au moins 2 couches (créer via « Nouvelle carte » du catalogue `<BASE>/` si absente ; ajouter 2 couches depuis le panneau Couches). Noter son `<pk>`.
- Critère de réussite global : toutes les étapes OK ; un seul KO = la lettre reste `externe` et le KO est consigné en `bug()` (REV-nnn à ouvrir).

## A. Appareil tactile réel (REV-286 c)
Matériel : un téléphone ou une tablette réels (iOS Safari ou Android Chrome), pas l'émulation DevTools. Noter modèle, OS, navigateur + version.
Stack : `<BASE>` (voir prérequis), auth OIDC. Ouvrir `<BASE>/maps/<pk>` après connexion.
1. Carte à 2 couches ouverte : pincer-zoomer, déplacer. Réussite : la carte zoome/se déplace et la page ne défile pas derrière (le corps de page reste à la même position).
2. Barre d'outils carte : bouton « Croquis », puis outil « Tracé libre ». Tracer au doigt une ligne d'environ 3 s. Réussite : un trait suit le doigt en continu, la page ne défile pas (`touch-action: none`), le trait reste affiché au relâchement.
3. « Tracé libre » : commencer un tracé, puis poser un 2e doigt, ou glisser le doigt hors de l'écran (touchcancel). Réussite : le tracé partiel disparaît (ABANDONNÉ, REV-286 e) ; aucun trait validé n'apparaît. Contre-épreuve : un tracé normal relâché à l'intérieur de l'écran, lui, reste.
4. Toucher une entité d'une couche (popup configuré ; sinon en configurer un dans le panneau de la couche). Réussite : le popup s'ouvre et reste entièrement dans l'écran ; pivoter l'appareil (portrait vers paysage) : le popup se recale dans l'écran (REV-286 d).
5. Tablette portrait, ou fenêtre de 640 à 899 px de large : mode 2 volets (lot C). Réussite : tous les panneaux lisibles, aucun scroll horizontal de la page, aucun texte ni bouton tronqué.
Relevé : pour chaque étape OK / KO + capture d'écran jointe (chemin, ex. `docs/revue/captures/`) + remarque.

## B. Lecteur d'écran réel (REV-284 d)
Logiciel : NVDA + Firefox (Windows) ou VoiceOver + Safari (macOS : Cmd+F5 pour l'activer ; NVDA : Ctrl+Alt+N). Noter versions. Cible : build courant, `<BASE>`, auth OIDC (compte du prérequis).
Raccourcis : NVDA liste des titres = Insert+F7, navigation titre suivant = `H` ; VoiceOver rotor = VO+U, titres via VO+Cmd+H.
1. Catalogue `<BASE>/` : saisir un terme dans la recherche. Réussite : le nombre de résultats est annoncé UNE fois (région `role="status"` sr-only) ; pas de double annonce avec le compteur visible. Le journal d'annonces du lecteur (NVDA : Visionneuse de parole, menu NVDA > Outils) en fait foi.
2. Navigation par titres (`H`) sur `<BASE>/` : `h1` de la page, `h2` « Résultats » avant la grille, `h3` des cartes. Puis `<BASE>/public` (catalogue public, sans connexion), ouvrir une entrée embed (`<BASE>/embed/<token>`, lien de partage généré depuis une app/dashboard) et un site publié (`<BASE>/sites/<slug>`). Réussite : chaque page annonce un `h1`.
3. Formulaire avec erreur : ouvrir un item en édition ou la création de collection, vider un champ obligatoire, valider. Réussite : le résumé d'erreurs est annoncé et le focus tombe sur le 1er champ invalide (lot C, REV-223).
4. Menu « Actions » d'une carte du catalogue (Radix) : Entrée pour ouvrir, Échap pour fermer. Réussite : ouverture et fermeture annoncées, focus restitué au bouton déclencheur.
5. Dialogue de suppression (`alertdialog`) : Actions > Supprimer sur un item jetable (ne pas confirmer, Échap). Réussite : intitulé ET description annoncés à l'ouverture, focus dans le dialogue, restitué au déclencheur à la fermeture.
Relevé : OK / KO + transcription du lecteur (copier le texte annoncé) + remarque.
