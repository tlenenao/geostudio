// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Variable } from "../api/types";

type SetVariable = (name: string, value: unknown) => void;

const VariablesContext = createContext<Record<string, unknown>>({});
const SetVariableContext = createContext<SetVariable>(() => {});

export function VariablesProvider({
  variables,
  children,
}: {
  variables: Variable[];
  children: ReactNode;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {};
    for (const v of variables) initial[v.name] = v.initialValue;
    return initial;
  });

  // Pick up a variable added after this provider mounted (e.g. the editor's
  // VariablesPanel adding one live) without resetting values already
  // changed at runtime for variables that already existed.
  useEffect(() => {
    setValues((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const v of variables) {
        if (!(v.name in next)) {
          next[v.name] = v.initialValue;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [variables]);

  function setVariable(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <SetVariableContext.Provider value={setVariable}>
      <VariablesContext.Provider value={values}>{children}</VariablesContext.Provider>
    </SetVariableContext.Provider>
  );
}

export function useVariables(): Record<string, unknown> {
  return useContext(VariablesContext);
}

export function useSetVariable(): SetVariable {
  return useContext(SetVariableContext);
}
