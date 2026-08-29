// SPDX-License-Identifier: Apache-2.0
// Sous-ensemble curaté de Lucide (ISC), 140 pictogrammes en 7 catégories
// cartographiques — PAS le jeu complet, qui compte 2035 fichiers dans
// lucide-static@1.34.0. Les SVG eux-mêmes vivent dans
// lucideIconSvgs.generated.ts, produit par scripts/gen-lucide-icons.mjs :
// lucide-static est une devDependency, rien n'est téléchargé au runtime.
import { LUCIDE_ICON_SVGS } from "./lucideIconSvgs.generated";

export type IconCategory =
  "generic" | "buildings" | "nature" | "transport" | "services" | "safety-health" | "leisure";

// Le script de génération lit ce bloc : garder la déclaration
// `const ICON_NAMES: Record<IconCategory, string[]> = {` **au caractère près**
// (le script s'y ancre par indexOf), un littéral de tableau par catégorie, des
// littéraux de chaîne, et 20 noms par catégorie. La clé "safety-health" est
// entre guillemets parce qu'elle contient un tiret ; le script n'extrait que
// l'intérieur des tableaux, donc elle n'est jamais comptée comme un nom
// d'icône (constat B3).
const ICON_NAMES: Record<IconCategory, string[]> = {
  generic: [
    "map-pin",
    "map-pinned",
    "pin",
    "flag",
    "star",
    "circle-dot",
    "target",
    "bookmark",
    "info",
    "alert-circle",
    "circle",
    "square",
    "triangle",
    "diamond",
    "compass",
    "navigation",
    "crosshair",
    "locate",
    "map",
    "route",
  ],
  buildings: [
    "building",
    "building-2",
    "home",
    "warehouse",
    "factory",
    "hotel",
    "church",
    "castle",
    "landmark",
    "tower-control",
    "radio-tower",
    "construction",
    "hard-hat",
    "fence",
    "door-open",
    "antenna",
    "school",
    "library",
    "university",
    "brick-wall",
  ],
  nature: [
    "tree-pine",
    "trees",
    "leaf",
    "flower",
    "flower-2",
    "mountain",
    "mountain-snow",
    "waves",
    "droplet",
    "droplets",
    "sun",
    "cloud",
    "cloud-rain",
    "wind",
    "sprout",
    "bird",
    "fish",
    "bug",
    "shell",
    "sunrise",
  ],
  transport: [
    "car",
    "bus",
    "train",
    "train-front",
    "tram-front",
    "bike",
    "plane",
    "ship",
    "truck",
    "fuel",
    "parking-circle",
    "parking-square",
    "traffic-cone",
    "signpost",
    "anchor",
    "sailboat",
    "car-taxi-front",
    "footprints",
    "cable-car",
    "rocket",
  ],
  services: [
    "shopping-cart",
    "shopping-bag",
    "store",
    "coffee",
    "utensils",
    "wine",
    "pizza",
    "croissant",
    "shirt",
    "scissors",
    "wrench",
    "briefcase",
    "credit-card",
    "banknote",
    "package",
    "gift",
    "mail",
    "phone",
    "wifi",
    "printer",
  ],
  "safety-health": [
    "hospital",
    "cross",
    "pill",
    "stethoscope",
    "syringe",
    "bandage",
    "heart-pulse",
    "thermometer",
    "ambulance",
    "life-buoy",
    "fire-extinguisher",
    "flame",
    "siren",
    "shield",
    "shield-alert",
    "shield-check",
    "alert-triangle",
    "phone-call",
    "biohazard",
    "radiation",
  ],
  leisure: [
    "camera",
    "binoculars",
    "eye",
    "ticket",
    "music",
    "palette",
    "book-open",
    "gamepad-2",
    "dumbbell",
    "volleyball",
    "trophy",
    "medal",
    "party-popper",
    "film",
    "theater",
    "guitar",
    "puzzle",
    "dice-5",
    "tent",
    "ferris-wheel",
  ],
};

export const LUCIDE_ICONS: { name: string; category: IconCategory }[] = (
  Object.entries(ICON_NAMES) as [IconCategory, string[]][]
).flatMap(([category, names]) => names.map((name) => ({ name, category })));

// Couleur de trait injectée : les SVG de lucide-static portent
// `stroke="currentColor"` (vérifié sur le paquet 1.34.0). Hors d'un document
// CSS — dans un <img> ou createImageBitmap — `currentColor` retombe sur la
// valeur initiale de `color`, donc noir. On substitue explicitement pour que
// l'icône ait la couleur voulue du dépôt, et pour que ce ne soit pas un
// hasard de résolution.
const LUCIDE_STROKE = "#1e293b";

const imageCache = new Map<string, Promise<HTMLImageElement>>();

// Décodage d'un blob d'image en quelque chose que map.addImage accepte.
// PAS createImageBitmap : sa prise en charge d'un blob SVG varie d'un
// navigateur à l'autre, et les icônes Lucide comme les icônes personnalisées
// peuvent être du SVG. `map.addImage(id, image, options?)` accepte
// `HTMLImageElement | ImageBitmap | ImageData | {width,height,data} |
// StyleImageInterface` (signature vérifiée dans maplibre-gl@4.7.1), donc un
// HTMLImageElement décodé depuis une URL d'objet convient pour les deux
// familles de type et n'a qu'un seul chemin de code.
export function decodeIconImage(blob: Blob): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(blob);
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image illisible"));
    img.src = url;
  }).finally(() => {
    // Révoquer dès le décodage : MapLibre copie les pixels dans son atlas au
    // moment de addImage, il ne relit jamais l'URL.
    URL.revokeObjectURL(url);
  });
}

export function rasterizeLucideIcon(name: string): Promise<HTMLImageElement> {
  const cached = imageCache.get(name);
  if (cached) return cached;
  const svg = LUCIDE_ICON_SVGS[name];
  if (svg === undefined) return Promise.reject(new Error(`Icône Lucide inconnue : ${name}`));
  // Substitution sur NOTRE propre asset de confiance, pas de
  // l'assainissement : `split`/`join` plutôt qu'une expression régulière
  // pour qu'aucun caractère spécial ne soit interprété.
  const painted = svg.split('stroke="currentColor"').join(`stroke="${LUCIDE_STROKE}"`);
  const promise = decodeIconImage(new Blob([painted], { type: "image/svg+xml" })).catch((err) => {
    // Ne pas mémoriser un échec : un rechargement doit pouvoir réessayer.
    imageCache.delete(name);
    throw err;
  });
  imageCache.set(name, promise);
  return promise;
}
