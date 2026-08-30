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
  "comingSoon.tasks": "Le centre de tâches arrive avec SP-31.",
  "comingSoon.settings": "Les paramètres d'instance arrivent avec SP-33.",

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
} as const;
