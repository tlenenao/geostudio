// SPDX-License-Identifier: Apache-2.0
// `setDataCalls` (SP-27 étiquettes) : compteur d'appels réels à `setData`,
// posé par `addSource` sur chaque source enregistrée — optionnel dans ce type
// exporté puisque seules les sources créées via `addSource` le portent.
export type Recorded = { id: string; spec: unknown; setDataCalls?: number };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: {
    style: string;
    center: [number, number];
    zoom: number;
    pitch?: number;
    bearing?: number;
    transformRequest?: (
      url: string,
      resourceType?: string,
    ) => { url: string; headers?: Record<string, string> };
  };
  handlers: Record<string, Array<(e?: unknown) => void>> = {};
  layerHandlers: Record<string, Array<(e: unknown) => void>> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  controls: unknown[] = [];
  removed = false;
  throwOnAddLayer = new Set<string>();
  flyToArgs: unknown[] = [];
  fitBoundsArgs: unknown[] = [];
  bounds: [[number, number], [number, number]] = [
    [0, 0],
    [0, 0],
  ];
  terrain: unknown = null;
  // Images ajoutées par map.addImage (SP-27 icônes). La valeur enregistrée
  // est le second argument tel quel : les tests n'inspectent que la présence
  // et l'éventuel objet d'options, jamais les pixels.
  images = new Map<string, { image: unknown; options?: unknown }>();
  // `glyphs` du style actif : `text-field` exige que le style en déclare un
  // (vérifié contre le validateur du style-spec installé). MapView refuse de
  // poser une couche d'étiquettes sans lui ; les tests le pilotent d'ici.
  glyphs: string | undefined = "https://glyphs.test/{fontstack}/{range}.pbf";
  // Réponses de querySourceFeatures, par id de source. Un test d'étiquettes
  // pose ici les entités que la carte est censée avoir chargées.
  sourceFeatures: Record<string, unknown[]> = {};
  querySourceFeaturesCalls: { sourceId: string; params?: unknown }[] = [];

  constructor(opts: MockMap["opts"]) {
    this.opts = opts;
    mapInstances.push(this);
  }

  on(event: string, arg2: string | (() => void), cb?: (e: unknown) => void) {
    if (typeof arg2 === "string" && cb) {
      const key = `${event}:${arg2}`;
      (this.layerHandlers[key] ??= []).push(cb);
    } else if (typeof arg2 === "function") {
      (this.handlers[event] ??= []).push(arg2);
      if (event === "load") arg2();
    }
    return this;
  }
  off(event: string, arg2: string | ((e: unknown) => void), cb?: (e: unknown) => void) {
    if (typeof arg2 === "function") {
      this.handlers[event] = (this.handlers[event] ?? []).filter((h) => h !== arg2);
      return this;
    }
    const key = `${event}:${arg2}`;
    this.layerHandlers[key] = (this.layerHandlers[key] ?? []).filter((h) => h !== cb);
    return this;
  }
  once(event: string, cb: () => void) {
    const wrapped = () => {
      this.handlers[event] = (this.handlers[event] ?? []).filter((h) => h !== wrapped);
      cb();
    };
    (this.handlers[event] ??= []).push(wrapped);
    return this;
  }
  fire(event: string, payload?: unknown) {
    // Iterate a snapshot: `once` handlers mutate this.handlers[event] while
    // firing, which would otherwise desync a live forEach mid-iteration.
    [...(this.handlers[event] ?? [])].forEach((cb) => (cb as (e?: unknown) => void)(payload));
  }
  fireOnLayer(event: string, layerId: string, payload: unknown) {
    this.layerHandlers[`${event}:${layerId}`]?.forEach((cb) => cb(payload));
  }
  addSource(id: string, spec: unknown) {
    // `setDataCalls` (SP-27 étiquettes) : compteur d'appels réels à `setData`
    // sur CETTE source — c'est ce que le test du garde d'idempotence de
    // `refreshLabelSources` (constat N3) observe pour prouver qu'un `idle`
    // sans changement d'entités ne repose pas la source.
    const rec: Recorded & { setData?: (d: unknown) => void; setDataCalls: number } = {
      id,
      spec,
      setDataCalls: 0,
    };
    rec.setData = (d: unknown) => {
      rec.spec = { ...(rec.spec as object), data: d };
      rec.setDataCalls += 1;
    };
    this.sources.push(rec);
  }
  addImage(id: string, image: unknown, options?: unknown) {
    this.images.set(id, { image, options });
    return this;
  }
  hasImage(id: string) {
    return this.images.has(id);
  }
  listImages() {
    return [...this.images.keys()];
  }
  flyTo(opts: unknown) {
    this.flyToArgs.push(opts);
  }
  fitBounds(bounds: unknown, opts?: unknown) {
    this.fitBoundsArgs.push({ bounds, opts });
  }
  addLayer(layer: { id: string; [k: string]: unknown }) {
    if (this.throwOnAddLayer.has(layer.id)) throw new Error(`boom ${layer.id}`);
    this.layers.push(layer);
  }
  getLayer(id: string) {
    return this.layers.find((l) => l.id === id);
  }
  getSource(id: string) {
    return this.sources.find((s) => s.id === id);
  }
  removeLayer(id: string) {
    this.layers = this.layers.filter((l) => l.id !== id);
  }
  removeSource(id: string) {
    this.sources = this.sources.filter((s) => s.id !== id);
  }
  getCenter() {
    return { lng: this.opts.center[0], lat: this.opts.center[1] };
  }
  getZoom() {
    return this.opts.zoom;
  }
  getBounds() {
    return { toArray: () => this.bounds };
  }
  getPitch() {
    return this.opts.pitch ?? 0;
  }
  getBearing() {
    return this.opts.bearing ?? 0;
  }
  setTerrain(spec: unknown) {
    this.terrain = spec;
  }
  loaded() {
    return true;
  }
  // Real MapLibre's isStyleLoaded() answers "is nothing loading right now?",
  // so a single in-flight (or failing) tile request flips it to false long
  // after the style's initial load. Tests flip `styleSettled` to reproduce
  // that window; MapView must not use it as a precondition for applying
  // config updates.
  styleSettled = true;
  isStyleLoaded() {
    return this.styleSettled;
  }
  getStyle() {
    return { glyphs: this.glyphs };
  }
  // MapView projette le point cliqué pour positionner le popup ; la valeur
  // exacte n'a pas de sens en test, seule sa propagation compte.
  project(lngLat: { lng: number; lat: number }) {
    return { x: Math.round(lngLat.lng), y: Math.round(lngLat.lat) };
  }
  querySourceFeatures(sourceId: string, params?: unknown) {
    this.querySourceFeaturesCalls.push({ sourceId, params });
    return this.sourceFeatures[sourceId] ?? [];
  }
  getCanvas() {
    // MapMeasureSketchToolbar ne lit que `style.cursor`.
    return { style: {} as Record<string, string> };
  }
  addControl(control: unknown) {
    this.controls.push(control);
    return this;
  }
  removeControl(control: unknown) {
    this.controls = this.controls.filter((c) => c !== control);
    return this;
  }
  remove() {
    this.removed = true;
  }
}
