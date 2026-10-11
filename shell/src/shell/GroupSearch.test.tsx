// SPDX-License-Identifier: Apache-2.0
// REV-277 : GET /groups ne renvoie que les groupes de l'appelant ; la recherche
// `?q=` (≥ 2 caractères, debouncée) atteint les autres dans les trois sélecteurs.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { CollectionSharePanel } from "./CollectionSharePanel";
import { GeoLimitsSection } from "./GeoLimitsSection";
import { ShareForm } from "./ShareForm";

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Mon app",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
  isPublished: false,
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

function Harness({ children }: { children: ReactNode }) {
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

const seen: (string | null)[] = [];
function mockServer() {
  seen.length = 0;
  server.use(
    http.get("https://core.test/v1/collections/c1/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.get("https://core.test/v1/collections/c1/geo-limits", () =>
      HttpResponse.json({ limits: [] }),
    ),
    http.get("https://core.test/v1/groups", ({ request }) => {
      const q = new URL(request.url).searchParams.get("q");
      seen.push(q);
      return HttpResponse.json(q ? [{ id: "g9", name: "Lointain", title: "Lointain" }] : []);
    }),
  );
}

const cases: [string, () => ReactNode, string][] = [
  ["ShareForm", () => <ShareForm item={item} onDone={vi.fn()} />, "checkbox"],
  [
    "CollectionSharePanel",
    () => <CollectionSharePanel collectionId="c1" onClose={vi.fn()} />,
    "checkbox",
  ],
  ["GeoLimitsSection", () => <GeoLimitsSection collectionId="c1" />, "option"],
];

test.each(cases)(
  "%s : la recherche interroge /groups?q= dès 2 caractères",
  async (_n, ui, role) => {
    mockServer();
    render(<Harness>{ui()}</Harness>);
    const search = await screen.findByRole("searchbox", { name: /rechercher un groupe/i });
    await userEvent.type(search, "l");
    await new Promise((r) => setTimeout(r, 350));
    expect(seen).not.toContain("l");
    await userEvent.type(search, "o");
    expect(await screen.findByRole(role, { name: /Lointain/ })).toBeInTheDocument();
    expect(seen).toContain("lo");
  },
);
