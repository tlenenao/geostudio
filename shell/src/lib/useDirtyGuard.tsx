// SPDX-License-Identifier: Apache-2.0
// Garde de navigation in-app sur brouillon non enregistré (SP-B6b, Tâche 26).
// Bloque une navigation interne (useBlocker, API data-router — nécessite la
// Tâche 25) tant que isDirty est vrai, et affiche ConfirmDialog pour laisser
// l'utilisateur confirmer ou annuler.
import { useCallback } from "react";
import { useBlocker, type BlockerFunction } from "react-router-dom";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { t } from "../i18n";

export function useDirtyGuard(isDirty: boolean) {
  const blocker = useBlocker(
    useCallback<BlockerFunction>(
      ({ currentLocation, nextLocation }) =>
        isDirty && currentLocation.pathname !== nextLocation.pathname,
      [isDirty],
    ),
  );

  // `ConfirmLeaveDialog` doit garder une identité de fonction stable entre
  // deux rendus du composant appelant qui ne changent pas l'état du blocker :
  // sans ce useCallback, une nouvelle fonction (donc un nouveau type de
  // composant, au sens de React) serait créée à chaque rendu du composant
  // appelant — y compris un rendu déclenché par une cause totalement sans
  // rapport (ex. un refetch de fond) pendant que la boîte de confirmation est
  // affichée. React démonterait alors et remonterait tout le sous-arbre
  // <ConfirmDialog> (nouveau nœud DOM, perte de focus/piège de focus Radix)
  // à chaque rendu du parent, alors que rien n'a réellement changé du point
  // de vue de la navigation.
  //
  // `[blocker]` suffit comme dépendance : `blocker` (retourné par
  // react-router-dom's useBlocker) est lu depuis `state.blockers` du routeur
  // data-router, un objet dont la référence n'est réassignée par
  // RouterProvider que lorsque le routeur notifie un changement d'état réel
  // (cf. `@remix-run/router/router.js`, `updateBlocker`/`State.blockers`
  // gérés en Map immuable ; `react-router-dom/RouterProvider` ne recrée son
  // `useState(router.state)` que via le callback `router.subscribe`, jamais
  // sur un rendu d'un composant descendant). Un rendu du composant appelant
  // déclenché par un état local ou une query sans rapport ne fait donc PAS
  // changer la référence de `blocker` : `ConfirmLeaveDialog` reste stable
  // exactement dans le cas qui nous intéresse, et change bien quand l'état du
  // blocker change réellement (idle -> blocked -> proceeding...), ce qui est
  // le seul moment où on veut que son rendu se mette à jour.
  const ConfirmLeaveDialog = useCallback(() => {
    if (blocker.state !== "blocked") return null;
    return (
      <ConfirmDialog
        open
        title={t("navigation.unsavedChangesTitle")}
        message={t("navigation.unsavedChangesMessage")}
        confirmLabel={t("navigation.leaveAnyway")}
        onCancel={() => blocker.reset()}
        onConfirm={() => blocker.proceed()}
      />
    );
  }, [blocker]);

  return { blocker, ConfirmLeaveDialog };
}
