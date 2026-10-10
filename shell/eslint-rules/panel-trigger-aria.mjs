// SPDX-License-Identifier: Apache-2.0
// REV-059/REV-088 : convention CLAUDE.md du 2026-09-01 — tout déclencheur de
// panneau en ligne porte aria-expanded + aria-controls (ou relaie
// usePanelTrigger().triggerProps). Faux positifs résiduels (rares) :
//   // eslint-disable-next-line geostudio/panel-trigger-aria -- <raison>
//
// REV-323 (lot C) : (1) le gestionnaire peut être un identifiant
// (`onClick={openPanel}`) résolu vers sa déclaration locale ; (2) `IconButton`
// du kit est un déclencheur comme `Button` ; (3) un setter dont le nom désigne
// un dialogue modal, un toast ou un état transitoire (`setConfirmOpen`,
// `setSaveDialogOpen`, `setCopied`, `setBusy`…) n'ouvre pas un panneau EN LIGNE :
// il est exclu plutôt que désactivé site par site. `Select` n'est pas
// concerné : un sélecteur Radix porte ses propres aria-* et n'ouvre rien via
// onClick.
const SETTER = /^set[A-Z]/;
const NOT_INLINE_PANEL =
  /Dialog|Drawer|Modal|Confirm|Toast|Copied|Saving|Busy|Pending|Loading|Deleting/;
const TRIGGERS = ["button", "Button", "IconButton"];

function isOpening(call) {
  const c = call.callee;
  if (
    c.type === "MemberExpression" &&
    c.property.type === "Identifier" &&
    c.property.name === "toggle"
  )
    return true;
  if (c.type !== "Identifier" || !SETTER.test(c.name) || call.arguments.length !== 1) return false;
  if (NOT_INLINE_PANEL.test(c.name)) return false;
  const a = call.arguments[0];
  if (a.type === "Literal" && a.value === true) return true;
  if (a.type === "UnaryExpression" && a.operator === "!") return true;
  return (
    a.type === "ArrowFunctionExpression" &&
    a.body.type === "UnaryExpression" &&
    a.body.operator === "!"
  );
}

function containsOpening(node, keys) {
  if (!node || typeof node.type !== "string") return false;
  if (node.type === "CallExpression" && isOpening(node)) return true;
  for (const key of keys[node.type] ?? []) {
    const child = node[key];
    if (
      Array.isArray(child)
        ? child.some((n) => containsOpening(n, keys))
        : containsOpening(child, keys)
    )
      return true;
  }
  return false;
}

// `onClick={handler}` : remonte la portée jusqu'à la déclaration locale du
// gestionnaire (fonction ou `const f = () => …`). Un gestionnaire importé ou
// reçu en prop reste invisible (limite assumée : pas de faux positif).
function resolveHandler(context, ident) {
  let scope = context.sourceCode.getScope(ident);
  while (scope) {
    const variable = scope.set.get(ident.name);
    if (variable) {
      for (const def of variable.defs) {
        if (def.type === "FunctionName") return def.node;
        if (def.type === "Variable" && def.node.init) return def.node.init;
      }
      return null;
    }
    scope = scope.upper;
  }
  return null;
}

export default {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      missing:
        "Déclencheur de panneau en ligne sans aria-expanded/aria-controls : relayer usePanelTrigger().triggerProps (shell/src/ui/kit/usePanelTrigger.ts).",
    },
  },
  create(context) {
    const keys = context.sourceCode.visitorKeys;
    return {
      JSXOpeningElement(node) {
        if (node.name.type !== "JSXIdentifier" || !TRIGGERS.includes(node.name.name)) return;
        const names = new Set();
        let spread = false;
        let onClick = null;
        for (const attr of node.attributes) {
          if (attr.type === "JSXSpreadAttribute") {
            const arg = attr.argument;
            if (arg.type === "Identifier" && arg.name === "triggerProps") spread = true;
            if (
              arg.type === "MemberExpression" &&
              arg.property.type === "Identifier" &&
              arg.property.name === "triggerProps"
            )
              spread = true;
          } else if (attr.name.type === "JSXIdentifier") {
            names.add(attr.name.name);
            if (attr.name.name === "onClick") onClick = attr.value;
          }
        }
        if (!onClick) return;
        let handler = onClick;
        const expr = onClick.type === "JSXExpressionContainer" ? onClick.expression : null;
        if (expr && expr.type === "Identifier") handler = resolveHandler(context, expr);
        if (!handler || !containsOpening(handler, keys)) return;
        if (spread || (names.has("aria-expanded") && names.has("aria-controls"))) return;
        context.report({ node, messageId: "missing" });
      },
    };
  },
};
