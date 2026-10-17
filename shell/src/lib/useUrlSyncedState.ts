// SPDX-License-Identifier: Apache-2.0
import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

export function useUrlSyncedState<T extends string>(
  paramName: string,
  defaultValue: T | null,
): [T | null, (value: T | null) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  // AUD-088 : sans `state`, la navigation `replace` effaçait location.state (titre du
  // pipeline neuf perdu au premier changement d'onglet).
  const location = useLocation();
  const raw = searchParams.get(paramName);
  const value = (raw as T | null) ?? defaultValue;

  const setValue = useCallback(
    (next: T | null) => {
      setSearchParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          if (next === null) {
            updated.delete(paramName);
          } else {
            updated.set(paramName, next);
          }
          return updated;
        },
        { replace: true, state: location.state },
      );
    },
    [paramName, setSearchParams, location.state],
  );

  return [value, setValue];
}
