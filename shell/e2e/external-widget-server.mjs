// shell/e2e/external-widget-server.mjs
//
// Minimal static file server for E2E: serves examples/external-widget/ on a
// port distinct from the shell's own preview server, with CORS enabled, so
// external-widget.spec.ts exercises a genuinely cross-origin dynamic
// import() — not the same-origin fixture path used by extension-widget.spec.ts.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../examples/external-widget/", import.meta.url));
const PORT = 4174;

const CONTENT_TYPES = {
  ".js": "application/javascript",
  ".json": "application/json",
};

createServer(async (req, res) => {
  const path = (req.url ?? "/").split("?")[0];
  const filePath = join(ROOT, path === "/" ? "widget.js" : path);
  try {
    const body = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": CONTENT_TYPES[extname(filePath)] ?? "application/octet-stream",
      "Access-Control-Allow-Origin": "*",
    });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
}).listen(PORT, () => {
  console.log(`external-widget-server listening on http://localhost:${PORT}`);
});
