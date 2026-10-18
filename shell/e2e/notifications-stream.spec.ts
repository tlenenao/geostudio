// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, READER_ME } from "./mocks";

// L13/D7 : le compteur de la cloche suit le flux SSE sans attendre le sondage de 45 s
// (qui répond 0 ici : seul le flux peut afficher 4).
test("la cloche affiche le compte poussé par le flux SSE", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  await page.route("https://core.test/v1/notifications/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: 'retry: 5000\n\nevent: notifications\ndata: {"unread": 4}\n\n',
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: /notifications/i }).getByText("4")).toBeVisible();
});
