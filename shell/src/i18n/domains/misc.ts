// SPDX-License-Identifier: Apache-2.0
// Domaine « misc » du catalogue : chargé avec les modules qui en consomment les clés
// (chaque consommateur importe ce fichier, garde : domains.test.ts).
import { registerMessages } from "../index";

export const misc = {
  // Actions sur un item
  "actions.menu": "Actions",
  "actions.menuFor": "Actions de {title}",
  "actions.edit": "Modifier",
  "actions.publish": "Publier",
  "actions.unpublish": "Dépublier",
  "actions.thumbnail": "Miniature",
  "actions.share": "Partager",
  "actions.delete": "Supprimer",
  "actions.scheduleReport": "Programmer un rapport",
  "actions.deleteTitle": "Supprimer l'élément",
  "actions.deleteMessage": "Supprimer « {title} » ? Cette action est irréversible.",
  "actions.saveFailed": "Échec de l'enregistrement.",
  "actions.uploadFailed": "Échec de l'envoi.",
  "actions.deleteFailed": "Échec de la suppression.",
  "actions.publishFailed": "Échec de la publication.",

  // Titres de document par vue (WCAG 2.4.2)
  "itemCard.open": "Ouvrir",
  "itemCard.openFor": "Ouvrir {title}",

  // Catalogue
  "catalog.countOne": "{n} élément",
  "catalog.countMany": "{n} éléments",
  "catalog.allOption": "Tous",
  "catalog.scopeMine": "Mes éléments",
  "catalog.scopeShared": "Partagés avec moi",
  "catalog.scopePublic": "Publics",
  "catalog.sortDateDesc": "Date de création (récent d'abord)",
  "catalog.sortDateAsc": "Date de création (ancien d'abord)",
  "catalog.sortUpdatedDesc": "Date de modification (récent d'abord)",
  "catalog.sortTitleAsc": "Titre (A→Z)",
  "catalog.sortTitleDesc": "Titre (Z→A)",
  "catalog.filterLabel": "Filtrer",
  "catalog.searchLabel": "Rechercher",
  "catalog.typeLabel": "Type",
  "catalog.scheduledReportsLink": "Rapports planifiés →",
  "catalog.bookmarksLink": "Signets →",
  "catalog.sqlLabLink": "SQL Lab →",
  "catalog.scopeLabel": "Portée",
  "catalog.sortByLabel": "Trier par",
  "catalog.ownerLabel": "Propriétaire",
  "catalog.keywordsLabel": "Mots-clés",
  "catalog.spatialSearchLabel": "Recherche spatiale",
  "catalog.spatialShow": "Afficher la carte",
  "catalog.spatialHide": "Masquer la carte",
  "catalog.loadError": "Erreur de chargement.",
  "catalog.emptyFilteredDescription": "Aucun élément ne correspond à ces filtres.",
  "catalog.emptyFilteredTitle": "Aucun résultat",
  "catalog.resultsHeading": "Résultats",
  "catalog.emptyNoFilterDescription":
    "Créez votre première carte, application ou jeu de données pour commencer.",
  "catalog.emptyBookmarksTitle": "Aucune vue enregistrée pour l'instant",
  "catalog.emptyBookmarksDescription":
    "Enregistrez une vue depuis une application pour la retrouver ici.",
  "catalog.emptyReportsTitle": "Aucun rapport pour l'instant",
  "catalog.emptyReportsDescription":
    "Programmez un rapport pour recevoir une vue enregistrée en PDF à intervalle régulier.",
  "catalog.emptyReportsAction": "Programmer un rapport",
  "catalog.emptyNoFilterTitle": "Aucun élément pour l'instant",
  "catalog.resetFilters": "Réinitialiser les filtres",
  "catalog.summaryLabel": "Résumé",
  "catalog.searchResultLabel": "Recherche",
  "catalog.spatialExtentLabel": "Emprise spatiale",
  "catalog.spatialMapTitle": "Carte de sélection de l'emprise",
  "catalog.spatialFieldsLegend": "Ou saisir l'emprise en degrés",
  "catalog.spatialWest": "Ouest (longitude min.)",
  "catalog.spatialSouth": "Sud (latitude min.)",
  "catalog.spatialEast": "Est (longitude max.)",
  "catalog.spatialNorth": "Nord (latitude max.)",
  "catalog.spatialApply": "Appliquer l'emprise",
  "catalog.spatialInvalid":
    "Emprise invalide : renseignez les quatre valeurs (ouest < est, sud < nord, longitude entre -180 et 180, latitude entre -90 et 90).",
  "catalog.spatialDrawAria": "Dessiner un rectangle de recherche spatiale",

  // Breadcrumb
  "breadcrumb.label": "Fil d'Ariane",

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

  // Motif de navigation partagé (lien de retour au catalogue depuis un écran
  // d'administration/édition en triptyque) — réutilisé par plusieurs pages.
  "nav.backToCatalog": "← Retour au catalogue",

  // SettingsNav (shell/chrome/SettingsNav.tsx) — panneau de gauche partagé
  // par la page Paramètres et les sept pages d'administration (fusion des
  // anciens domaines "admin"/"settings", capabilities.ts) : "Général" est
  // toujours visible, les sept liens admin restent filtrés par privilège
  // comme la barre de domaines — un privilège manquant masque le lien.
  "settingsNav.label": "Navigation des paramètres",
  "settingsNav.linkGeneral": "Général →",
  "quota.itemsExceeded":
    "Quota d'éléments atteint ({current}/{limit}) : supprimez des éléments inutiles ou demandez à un administrateur d'augmenter la limite (Administration > Infrastructure).",
  "quota.collectionsExceeded":
    "Quota de collections atteint ({current}/{limit}) : supprimez des collections inutiles ou demandez à un administrateur d'augmenter la limite (Administration > Infrastructure).",
  "quota.storageExceeded":
    "Quota de stockage atteint ({current}/{limit}) : le fichier a été refusé. Supprimez des fichiers ou demandez à un administrateur d'augmenter la limite (Administration > Infrastructure).",

  // ItemDetailPage
  "itemDetail.notFound": "Élément introuvable.",
  "itemDetail.elementLabel": "Élément",
  "itemDetail.ownerLabel": "Propriétaire : {owner}",
  "itemDetail.openEditor": "Ouvrir dans l'éditeur",
  "itemDetail.editorUnavailableTitle": "Éditeur indisponible pour ce type",
  "publish.title": "Publier",
  "publish.privateCollections":
    "Cet élément lit des collections qui ne sont pas publiques : un visiteur anonyme verrait l'élément sans ses données.",
  "publish.itemOnly": "Publier sans les collections",
  "publish.withCollections": "Publier aussi les collections",
  "publish.collectionsFailed": "Échec de la publication des collections.",

  // ConfigHistoryPanel (builder)
  "configHistory.heading": "Historique",
  "configHistory.loadError": "Impossible de charger l'historique des versions.",
  "configHistory.restoreError": "Impossible de restaurer cette version.",
  "configHistory.empty": "Aucune version enregistrée.",
  "configHistory.versionLabel": "Version {version} — {date}",
  "configHistory.currentLabel": "(courante)",
  "configHistory.restoreButton": "Restaurer",
  "configHistory.confirmTitle": "Restaurer cette version ?",
  "configHistory.confirmMessage":
    "Restaurer la version {version} ? Les modifications non enregistrées seront perdues.",
  "resourceType.app": "Application",
  "resourceType.dashboard": "Tableau de bord",
  "resourceType.map": "Carte",
  "resourceType.site": "Site",
  "resourceType.dataset": "Jeu de données",
  "resourceType.bookmark": "Vue enregistrée",
  "resourceType.pipeline": "Pipeline",
  "resourceType.alert": "Alerte",
  "resourceType.report": "Rapport",
  "resourceType.tileset3d": "Tuiles 3D",
  "resourceType.terrain3d": "Terrain 3D",
  "resourceType.external": "Externe",
  "desktop.startupError": "Erreur de démarrage : {message}",
  "icon.unknown": "Icône Lucide inconnue : {name}",

  // Catalogue public, SEO et parcours lecteur (P35)
  "publicPage.notFound": "Page introuvable.",
  "publicPage.notFoundHeading": "Page publique",
  "publicCatalog.title": "Catalogue public",
  "publicCatalog.description": "Cartes, applications, sites et jeux de données publiés.",
  "publicCatalog.typeLabel": "Type",
  "publicCatalog.allTypes": "Tous les types",
  "publicCatalog.tagLabel": "Mot-clé",
  "publicCatalog.empty": "Aucun contenu public pour le moment.",
  "publicCatalog.loadError": "Impossible de charger le catalogue public.",
  "publicCatalog.previous": "Page précédente",
  "publicCatalog.next": "Page suivante",
  "publicCatalog.pageOf": "Page {page} sur {pages}",
  "itemDetail.openView": "Ouvrir",
  "itemDetail.licenseLabel": "Licence",
  "itemDetail.keywordsLabel": "Mots-clés",
  "itemDetail.languageLabel": "Langue",
  "itemDetail.columnsLabel": "Colonnes",
  "itemDetail.featureCountLabel": "Volume",
  "itemDetail.publicUrlLabel": "URL publique",
  "itemDetail.copyUrl": "Copier l'URL",
  "itemDetail.urlCopied": "URL copiée.",
  "itemDetail.slugInvalid": "Slug invalide : minuscules, chiffres et tirets uniquement.",
  // Exploration automatique d'un jeu de données (REV-117)
  "datasetProfile.toggle": "Explorer",
  "datasetProfile.title": "Profil des données",
  "datasetProfile.pending": "Les données ne sont pas encore disponibles pour l'exploration.",
  "datasetProfile.empty": "Aucune donnée à explorer.",
  "datasetProfile.rows": "{n} lignes",
  "datasetProfile.sampled": "Statistiques calculées sur un échantillon.",
  "datasetProfile.truncatedColumns": "Seules les premières colonnes sont profilées.",
  "datasetProfile.asOf": "À jour au {date}",
  "datasetProfile.colName": "Colonne",
  "datasetProfile.colType": "Type",
  "datasetProfile.colFill": "Renseigné",
  "datasetProfile.colDistinct": "Valeurs distinctes",
  "datasetProfile.colSummary": "Résumé",
  "datasetProfile.range": "{min} à {max}",
  "datasetProfile.median": "médiane {n}",
  "datasetProfile.histogram": "Répartition de {name}",
  "datasetProfile.geometry": "Géométrie ({column})",
  "datasetProfile.extent": "Emprise : {bbox}",
} as const;

registerMessages(misc);
