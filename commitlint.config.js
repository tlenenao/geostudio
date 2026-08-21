// Forme avec chemin complet : la forme "@commitlint/config-conventional" (bare package name) ne
// résout pas depuis la racine du dépôt (pas de package.json/node_modules root).
// Le preset vit dans shell/node_modules après `cd shell && npm ci` (cf. CLAUDE.md § Commandes).
module.exports = { extends: ["./shell/node_modules/@commitlint/config-conventional"] };
