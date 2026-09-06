// SPDX-License-Identifier: Apache-2.0
//
// Le catalogue de messages français. Seule langue livrée (arbitrage A12) : la
// couche existe pour que SP-30 extraie les libellés au moment où il réécrit
// les écrans, pas pour livrer une seconde langue aujourd'hui.
//
// Convention de clé : <domaine>.<intention>, en camelCase. Les paramètres
// s'écrivent {nom}.

export const fr = {
  // Actions sur un item
  "actions.menu": "Actions",
  "actions.edit": "Modifier",
  "actions.publish": "Publier",
  "actions.unpublish": "Dépublier",
  "actions.thumbnail": "Miniature",
  "actions.share": "Partager",
  "actions.delete": "Supprimer",
  "actions.scheduleReport": "Programmer un rapport",
  "actions.editTitle": "Modifier l'élément",
  "actions.thumbnailTitle": "Miniature",
  "actions.deleteTitle": "Supprimer l'élément",
  "actions.deleteMessage": "Supprimer « {title} » ? Cette action est irréversible.",
  "actions.saveFailed": "Échec de l'enregistrement.",
  "actions.uploadFailed": "Échec de l'envoi.",
  "actions.deleteFailed": "Échec de la suppression.",
  "actions.publishFailed": "Échec de la publication.",

  // Traitement « verrouillé et expliqué » — la raison ET le recours
  "locked.needWrite": "Modification réservée aux éditeurs de cet élément.",
  "locked.needShare": "Partage réservé au propriétaire et aux éditeurs.",
  "locked.needDelete": "Suppression réservée au propriétaire et aux éditeurs.",
  "locked.capabilityOff": "Désactivé sur cette instance — voir un administrateur.",

  // Chrome de page (AppLayout)
  "layout.readOnlyBanner": "Mode démo — lecture seule, les modifications ne sont pas enregistrées.",

  // Domaines
  "domain.catalog": "Catalogue",
  "domain.maps": "Cartes",
  "domain.data": "Données",
  "domain.apps": "Apps & sites",
  "domain.automation": "Automatisation",
  "domain.analytics": "Analytique",
  "domain.tasks": "Tâches",
  "domain.admin": "Administration",
  "domain.settings": "Paramètres",
  "domainBar.label": "Domaines",
  "bottomNav.label": "Navigation",
  "bottomNav.more": "Plus",
  "comingSoon.settings": "Les paramètres d'instance arrivent avec SP-33.",

  // UsagePage (/tasks) — journal d'activité (audit_log en lecture), pas un
  // tableau de bord de supervision temps réel des jobs (SP-47 §7)
  "usage.detail": "Détail",
  "usage.myTasks": "Mes tâches récentes",
  "usage.noTasks": "Aucune tâche récente.",
  "usage.columnAction": "Action",
  "usage.columnResource": "Ressource",
  "usage.columnDate": "Date",
  "usage.platformUsage": "Usage de la plateforme",
  "usage.byActor": "Par utilisateur",
  "usage.byResource": "Par ressource",
  "usage.loadFailed": "Échec du chargement des tâches.",
  "usage.summaryLoadFailed": "Échec du chargement de l'usage de la plateforme.",
  "usage.previous": "Précédent",
  "usage.next": "Suivant",
  "usage.pageOf": "Page {page} / {totalPages}",
  // Libellés français par action de JOB_AUDIT_ACTIONS
  // (core/app/usage/service.py) — tenu synchronisé manuellement, comme
  // BUILT_IN_ROLE_PRIVILEGES/CREATOR_ME (même classe de duplication
  // assumée que les fixtures de rôle, cf. SP-47 Task 2).
  "usageAction.ingestionJobCreate": "Import de données",
  "usageAction.pipelineRun": "Exécution de pipeline",
  "usageAction.exportCreate": "Création d'export",
  "usageAction.exportRun": "Exécution d'export",
  "usageAction.appexportCreate": "Export d'application",
  "usageAction.reportRun": "Génération de rapport",
  "usageAction.reportNotify": "Notification de rapport",
  "usageAction.alertEvaluate": "Évaluation d'alerte",
  "usageAction.alertNotify": "Notification d'alerte",
  "usageAction.harvestSourceRun": "Moissonnage",
  "usageAction.tileset3dJobCreate": "Traitement de jeu de tuiles 3D",
  "usageAction.terrain3dJobCreate": "Traitement de terrain 3D",

  // Catalogue
  "catalog.count": "{n} éléments",

  // NumberField
  "numberField.increase": "Augmenter",
  "numberField.decrease": "Diminuer",

  // Breadcrumb
  "breadcrumb.label": "Fil d'Ariane",

  // Toast
  "toast.close": "Fermer la notification",

  // ConfirmDialog
  "confirmDialog.cancel": "Annuler",

  // Combobox
  "combobox.noResults": "Aucun résultat",

  // Chip
  "chip.remove": "Retirer {item}",
  "chip.removeGeneric": "Retirer",

  // DataTable
  "dataTable.selectRow": "Sélectionner {item}",
  "dataTable.selectRowGeneric": "Sélectionner la ligne",

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
  "notifications.deletedItem": "Élément supprimé",
  "notifications.loadError": "Échec du chargement des notifications.",
  "notifications.actionError": "Échec de l'action. Réessayez.",

  // Administration des rôles
  "roles.title": "Rôles",
  "roles.addRole": "Ajouter un rôle",
  "roles.nameLabel": "Nom",
  "roles.privilegesLabel": "Privilèges",
  "roles.builtInBadge": "Prédéfini",
  "roles.deleteConfirmTitle": "Supprimer le rôle",
  "roles.deleteConfirmMessage": "Supprimer le rôle « {name} » ? Cette action est irréversible.",
  "roles.deleteBlockedByUsage": "Encore attribué à {count} utilisateur(s).",
  "roles.privilege.catalogManage": "Créer et modifier les éléments du catalogue",
  "roles.privilege.mapsManage": "Créer et modifier des cartes",
  "roles.privilege.dataView": "Voir le domaine Données",
  "roles.privilege.dataManage": "Créer et modifier des jeux de données",
  "roles.privilege.appsManage": "Créer et modifier des apps et sites",
  "roles.privilege.automationManage": "Créer et modifier des pipelines",
  "roles.privilege.automationSecretsManage": "Voir et gérer les noms de secrets",
  "roles.privilege.analyticsView": "Voir le domaine Analytique",
  "roles.privilege.analyticsSqlLabAccess": "Utiliser SQL Lab",
  "roles.privilege.tasksView": "Voir ses tâches",
  "roles.privilege.tasksViewAll": "Voir les tâches de tout le tenant",
  "roles.privilege.adminUsersManage": "Gérer les utilisateurs",
  "roles.privilege.adminRolesManage": "Gérer les rôles",
  "roles.privilege.adminHarvestManage": "Gérer le moissonnage",
  "roles.privilege.adminCollectionsManage": "Gérer les collections",
  "roles.privilege.adminExtensionsManage": "Gérer les extensions",
  "roles.privilege.adminSecretsManage": "Voir les noms de secrets (administration)",
  "roles.privilege.settingsInstanceManage": "Gérer les paramètres d'instance et de tenant",
  "roles.privilege.complianceManage": "Purger toutes les données d'un tenant (RGPD, irréversible)",
} as const;
