// SPDX-License-Identifier: Apache-2.0
// REV-226 : un contrôle dans un <label> visible ne doit pas porter aria-label/
// aria-labelledby — le nom accessible masquerait le texte visible du label.
// `Select` du kit exclu : son type impose `aria-label` (nom du déclencheur Radix).
const CONTROLS = new Set(["input", "select", "textarea", "Input", "Textarea"]);

function hasNameAttr(opening) {
  return opening.attributes.some(
    (a) =>
      a.type === "JSXAttribute" &&
      a.name.type === "JSXIdentifier" &&
      ["aria-label", "aria-labelledby"].includes(a.name.name),
  );
}

function findOffender(node, keys) {
  if (!node || typeof node.type !== "string") return null;
  if (
    node.type === "JSXOpeningElement" &&
    node.name.type === "JSXIdentifier" &&
    CONTROLS.has(node.name.name) &&
    hasNameAttr(node)
  )
    return node;
  for (const key of keys[node.type] ?? []) {
    const child = node[key];
    const hit = Array.isArray(child)
      ? child.map((n) => findOffender(n, keys)).find(Boolean)
      : findOffender(child, keys);
    if (hit) return hit;
  }
  return null;
}

export default {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      dup: "Contrôle dans un <label> avec aria-label/aria-labelledby : le nom accessible masque le texte visible du label. Retirer l'attribut (REV-226).",
    },
  },
  create(context) {
    const keys = context.sourceCode.visitorKeys;
    return {
      JSXElement(node) {
        const o = node.openingElement;
        if (o.name.type !== "JSXIdentifier" || o.name.name !== "label") return;
        const hit = node.children.map((c) => findOffender(c, keys)).find(Boolean);
        if (hit) context.report({ node: hit, messageId: "dup" });
      },
    };
  },
};
