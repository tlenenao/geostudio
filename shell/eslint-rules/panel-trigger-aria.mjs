// SPDX-License-Identifier: Apache-2.0
// REV-059/REV-088 : convention CLAUDE.md du 2026-09-01 — tout déclencheur de
// panneau en ligne porte aria-expanded + aria-controls (ou relaie
// usePanelTrigger().triggerProps). Faux positifs (dialogue modal, toast) :
//   // eslint-disable-next-line geostudio/panel-trigger-aria -- <raison>
const SETTER = /^set[A-Z]/;

function isOpening(call) {
  const c = call.callee;
  if (
    c.type === "MemberExpression" &&
    c.property.type === "Identifier" &&
    c.property.name === "toggle"
  )
    return true;
  if (c.type !== "Identifier" || !SETTER.test(c.name) || call.arguments.length !== 1) return false;
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
        if (node.name.type !== "JSXIdentifier" || !["button", "Button"].includes(node.name.name))
          return;
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
        if (!onClick || !containsOpening(onClick, keys)) return;
        if (spread || (names.has("aria-expanded") && names.has("aria-controls"))) return;
        context.report({ node, messageId: "missing" });
      },
    };
  },
};
