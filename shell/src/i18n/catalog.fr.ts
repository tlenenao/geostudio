// SPDX-License-Identifier: Apache-2.0
//
// Le noyau du catalogue de messages français (clés du chemin de démarrage ;
// les clés des domaines chargés à la demande sont sous ./domains/). Seule langue livrée (arbitrage A12) : la
// couche existe pour que SP-30 extraie les libellés au moment où il réécrit
// les écrans, pas pour livrer une seconde langue aujourd'hui.
//
// Convention de clé : <domaine>.<intention>, en camelCase. Les paramètres
// s'écrivent {nom}.

export const fr = {
  // Traitement « verrouillé et expliqué » — la raison ET le recours
  "locked.needWrite": "Modification réservée aux éditeurs de cet élément.",
  "locked.needShare": "Partage réservé au propriétaire et aux éditeurs.",
  "locked.capabilityOff": "Désactivé sur cette instance — voir un administrateur.",

  // Chrome de page (AppLayout)
  "layout.skipToContent": "Aller au contenu principal",
  "layout.readOnlyBanner": "Mode démo — lecture seule, les modifications ne sont pas enregistrées.",

  "docTitle.format": "{view} — GeoStudio",
  "docTitle.appName": "GeoStudio",
  "docTitle.catalog": "Catalogue",
  "docTitle.item": "Fiche de l'élément",
  "docTitle.bookmarks": "Signets",
  "docTitle.map": "Éditeur de carte",
  "docTitle.appEdit": "Éditeur d'application",
  "docTitle.datasetEdit": "Éditeur de jeu de données",
  "docTitle.pipelineNew": "Nouveau pipeline",
  "docTitle.pipelineEdit": "Éditeur de pipeline",
  "docTitle.visualQueryNew": "Nouvelle requête visuelle",
  "docTitle.visualQueryEdit": "Requête visuelle",
  "docTitle.reports": "Rapports",
  "docTitle.reportNew": "Nouveau rapport",
  "docTitle.reportEdit": "Édition du rapport",
  "docTitle.sqlLab": "SQL Lab",
  "docTitle.adminExtensions": "Extensions",
  "docTitle.adminCollections": "Collections",
  "docTitle.adminHarvest": "Moissonnage",
  "docTitle.adminRoles": "Rôles",
  "docTitle.adminUsers": "Utilisateurs",
  "docTitle.adminCompliance": "Conformité",
  "docTitle.adminInfrastructure": "Infrastructure",
  "docTitle.kitGallery": "Galerie du kit",
  "docTitle.tasks": "Tâches",
  "docTitle.settings": "Paramètres",
  "docTitle.app": "Application",
  "docTitle.embed": "Contenu intégré",
  "docTitle.site": "Portail",
  "docTitle.publicItem": "Élément public",
  "docTitle.publicDataset": "Jeu de données public",

  // Domaines
  "domain.catalog": "Catalogue",
  "domain.maps": "Cartes",
  "domain.data": "Données",
  "domain.apps": "Apps & sites",
  "domain.automation": "Automatisation",
  "domain.analytics": "Analytique",
  "domain.tasks": "Tâches",
  "domain.settings": "Paramètres",
  "domainBar.label": "Domaines",
  "bottomNav.label": "Navigation",
  "bottomNav.more": "Plus",

  // Palette de commandes ⌘K (D07, SP-C4/Task 21)
  "commandPalette.title": "Palette de commandes",
  "commandPalette.searchAria": "Rechercher une action",
  "commandPalette.newItemAction": "Nouvel élément",
  "commandPalette.triggerLabel": "Rechercher",
  "topbar.actions": "Actions",

  // Motif partagé : bouton générique d'effacement d'un filtre/champ.
  "common.clear": "Effacer",

  // Motif partagé : bouton de nouvelle tentative après une erreur de chargement.
  "common.retry": "Réessayer",
  // Motif partagé : lecture en échec (hors 404/403) et accès refusé.
  "common.loadError": "Erreur de chargement.",
  "common.accessDenied": "Accès refusé.",

  // Toast
  "toast.close": "Fermer la notification",
  "toast.providerMissing": "useToast doit être utilisé sous ToastProvider",
  "toast.mapSaved": "Carte enregistrée",
  "toast.datasetSaved": "Données enregistrées",
  "toast.appSaved": "Application enregistrée",
  "toast.pipelineCreated": "Pipeline créé",
  "toast.pipelineSaved": "Pipeline enregistré",
  "toast.webhookTokenCreated": "Jeton de webhook créé",
  "toast.webhookTokenRevoked": "Jeton de webhook révoqué",
  "toast.reportScheduleCreated": "Rapport planifié créé",
  "toast.reportScheduleSaved": "Rapport planifié enregistré",

  // AccountMenu
  "account.menu": "Compte",
  "account.roleAdmin": "Administrateur",
  "account.roleAnalyst": "Analyste",
  "account.roleCreator": "Créateur",
  "account.roleReader": "Lecteur",
  "account.signOut": "Déconnexion",

  // Notifications (SP-39, chantier 4.19)
  "notifications.bell": "Notifications",
  "notifications.empty": "Aucune notification.",
  "notifications.markAllRead": "Tout marquer comme lu",
  "notifications.preferenceAll": "Tous",
  "notifications.preferenceFailuresOnly": "Échecs seulement",
  "notifications.preferenceNone": "Aucune",
  "notifications.statusSuccess": "Succès",
  "notifications.statusFailure": "Échec",
  "notifications.kindIngestion": "Import",
  "notifications.kindPipeline": "Pipeline",
  "notifications.kindExport": "Export",
  "notifications.kindAppexport": "Export d'app",
  "notifications.kindReport": "Rapport",
  "notifications.kindAlert": "Alerte",
  "notifications.kindHarvest": "Moissonnage",
  "notifications.kindTileset3d": "Tileset 3D",
  "notifications.kindTerrain3d": "Terrain 3D",
  "notifications.kindDataExport": "Export de données",
  "notifications.panel": "Centre de notifications",
  "notifications.preference": "Préférence de notification",
  "notifications.unread": "Non lue",
  "notifications.loadMore": "Charger plus",
  "notifications.deletedItem": "Élément supprimé",
  "notifications.loadError": "Échec du chargement des notifications.",
  "notifications.actionError": "Échec de l'action. Réessayez.",

  // SettingsPage (pages/SettingsPage.tsx) — espace personnel : profil en
  // lecture seule (identité gérée par Keycloak), préférence de notifications
  // (déjà servie par le cœur, GET/PATCH /notifications/preference), lien
  // vers la console de compte Keycloak (masqué en mode mock).
  "settings.heading": "Paramètres",
  "settings.detail": "Aide",
  "settings.helpText":
    "Ces réglages sont personnels : ils ne sont visibles que par vous, pas partagés avec les autres utilisateurs.",
  "settings.profileTitle": "Profil",
  "settings.profileUsername": "Nom d'utilisateur",
  "settings.profileEmail": "Email",
  "settings.profileName": "Nom complet",
  "settings.profileRole": "Rôle",
  "settings.profileTenant": "Tenant",
  "settings.notificationsTitle": "Notifications",
  "settings.notificationsAll": "Toutes",
  "settings.notificationsFailuresOnly": "Échecs seulement",
  "settings.notificationsNone": "Aucune",
  "settings.notificationsSaveError": "Échec de l'enregistrement de la préférence.",
  "settings.appearanceTitle": "Apparence",
  "settings.appearanceAuto": "Automatique (suit le système)",
  "settings.appearanceLight": "Clair",
  "settings.appearanceDark": "Sombre",
  "settings.accountTitle": "Compte",
  "settings.accountKeycloakLink":
    "Gérer mon compte (mot de passe, authentification à deux facteurs) →",

  // Motif partagé : indicateur de chargement générique (role="status").
  "common.loading": "Chargement…",

  // Motifs partagés supplémentaires (SP-57a, lot builder/widgets) : états
  // génériques de données répétés à l'identique par presque tous les widgets.
  "common.dataError": "Erreur de données",
  "common.noData": "Aucune donnée",
  "common.sourceMissing": "Source de données introuvable",

  // Motif partagé : bouton d'enregistrement générique.
  "common.save": "Enregistrer",
  "common.saveConflict":
    "Cet objet a été modifié ailleurs depuis votre ouverture : votre enregistrement a été refusé pour ne pas écraser ces changements.",
  "common.saveConflictReload": "Recharger la dernière version",

  // ComplianceAdminPage
  "compliance.title": "Conformité",
  "compliance.heading": "Conformité (RGPD)",
  "compliance.detail": "Détail",
  "compliance.helpText":
    "Deux actions distinctes : anonymiser un compte (effet limité, réversible dans ses conséquences pratiques) et purger tout le tenant (irréversible). Ne jamais confondre l'une avec l'autre.",
  "compliance.eraseSectionTitle": "Anonymiser un compte",
  "compliance.eraseDescription":
    "Écrase le nom d'utilisateur, l'email et l'identité de connexion d'un compte. Les objets qu'il possède (cartes, collections, pièces jointes) restent intacts, attribués au compte anonymisé. Effet limité — le tenant continue de fonctionner normalement.",
  "compliance.userIdLabel": "Identifiant de l'utilisateur (ou « me » pour votre propre compte)",
  "compliance.eraseButton": "Anonymiser ce compte",
  "compliance.eraseSuccess": "Compte anonymisé.",
  "compliance.eraseError": "Échec de l'anonymisation.",
  "compliance.eraseNotFound": "Utilisateur introuvable dans ce tenant.",
  "compliance.eraseAlreadyErased": "Ce compte est déjà anonymisé.",
  "compliance.eraseLastHolder":
    "Impossible : ce compte est le dernier titulaire d'un privilège de gestion des utilisateurs ou des rôles.",
  "compliance.eraseForbidden": "Droits insuffisants pour anonymiser ce compte.",
  "compliance.purgeRequestError": "Échec du déclenchement de la purge.",
  "compliance.purgeSectionTitle": "Purger toutes les données du tenant",
  "compliance.purgeWarningBefore": "Supprime",
  "compliance.purgeWarningEmphasis": "irréversiblement",
  "compliance.purgeWarningAfter":
    "toutes les données de ce tenant : items, collections (y compris leurs tables), utilisateurs, rôles, pièces jointes, journal d'audit — puis le tenant lui-même. Aucune restauration possible après confirmation.",
  "compliance.confirmSlugBefore": "Retapez le slug du tenant (",
  "compliance.confirmSlugAfter": ") pour confirmer",
  "compliance.purgeButton": "Purger définitivement ce tenant",
  "compliance.purgeInProgress": "Purge en cours…",
  "compliance.purgeCompleted": "Purge terminée à {completedAt}.",
  // SP-B5 : {seconds} interpolé depuis ApiError.retryAfter (429, Retry-After).
  "errors.retryAfter": "Réessayez dans {seconds} s.",

  // routes.tsx — messages d'accès refusé (RequirePrivilege) et d'échec
  // d'ouverture d'item (distinct de locked.* : garde de route entière, pas
  // une action sur un item déjà ouvert)
  "routes.analystOnly": "Accès réservé aux analystes.",
  "routes.automationOnly": "Accès réservé à l'automatisation (privilège automation.manage requis).",
  "routes.visualQueryOnly":
    "La requête visuelle produit un jeu de données : elle exige les privilèges automation.manage et data.manage.",
  "routes.adminOnly": "Accès réservé aux administrateurs.",
  "routes.rolesOnly": "Accès réservé à la gestion des rôles.",
  "routes.usersOnly": "Accès réservé à la gestion des utilisateurs.",
  "routes.complianceOnly": "Accès réservé à la conformité (RGPD).",
  "routes.tasksOnly": "Accès réservé — privilège tasks.view requis.",
  "routes.openItemError": "Échec de l'ouverture de l'élément.",
  "routes.openBookmarkError": "Échec de l'ouverture du signet.",
  "routes.openReportError": "Échec de l'ouverture du rapport.",
  "aggregate.count": "Nombre",
  "aggregate.countDistinct": "Nombre de valeurs distinctes",
  "aggregate.sum": "Somme",
  "aggregate.avg": "Moyenne",
  "aggregate.median": "Médiane",
  "aggregate.percentile": "Centile",
  "aggregate.stddev": "Écart-type",
  "aggregate.min": "Min",
  "aggregate.max": "Max",
  "errors.coreUnreachable": "Le cœur GeoStudio est injoignable",
  "errors.invalidSql": "Requête SQL invalide.",
  "errors.groupMemberForbidden":
    "Ce groupe n'existe pas, ou vous n'en êtes pas le créateur — seul le créateur d'un groupe peut y ajouter un membre.",
  "template.two": "Deux colonnes",
  "template.basicDashboard": "Tableau de bord basique",
  "template.incidentApp": "Application de saisie",
  "template.story": "Story cartographique",
  "template.portal": "Portail de données",

  // ConnectivityBanner (SP-B7) — bannière globale sur injoignabilité du cœur
  "connectivity.unreachable": "Connexion au serveur perdue — nouvelle tentative en cours…",
  "connectivity.offline": "Vous êtes hors ligne — les données ne sont pas rechargées.",

  // jobStatusLabel (SP-B10a) — vocabulaire d'état de job partagé entre
  // PipelineRunPanel et ReportRunPanel (deux énumérations réelles distinctes,
  // cf. commentaire de shell/src/lib/jobStatusLabel.ts) : "queued"/"pending",
  // "succeeded"/"done" et "failed"/"error" sont des synonymes qui reçoivent le
  // même libellé. "cancelled" n'est émis par aucune API à ce jour.
  "jobStatus.pending": "En attente",
  "jobStatus.queued": "En attente",
  "jobStatus.running": "En cours",
  "jobStatus.succeeded": "Terminé",
  "jobStatus.done": "Terminé",
  "jobStatus.failed": "Échoué",
  "jobStatus.error": "Échoué",
  "jobStatus.cancelled": "Annulé",
  "jobStatus.cancelRequested": "Annulation demandée",
  "jobStatus.unknown": "Inconnu",
  "docTitle.publicCatalog": "Catalogue public",
} as const;
