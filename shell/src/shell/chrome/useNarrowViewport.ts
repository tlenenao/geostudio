// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

const QUERY = "(max-width: 389px)";

export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setNarrow(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return narrow;
}
