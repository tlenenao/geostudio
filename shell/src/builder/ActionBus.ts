import type { ActionMessage } from "../api/types";

export type BusHandler = (payload?: unknown) => void;

// Per-app event bus. Widgets emit events and register actions; the renderer
// wires config.messages so emitting an event invokes the target action(s).
// Keys join id + name with a space; ids are UUIDs / fixed literals (no spaces), so keys don't collide in practice.
export class ActionBus {
  private actions = new Map<string, BusHandler>();
  private wiring = new Map<string, ActionMessage[]>();

  configure(messages: ActionMessage[]): void {
    this.wiring.clear();
    for (const m of messages) {
      const key = `${m.from} ${m.event}`;
      const list = this.wiring.get(key) ?? [];
      list.push(m);
      this.wiring.set(key, list);
    }
  }

  register(widgetId: string, action: string, handler: BusHandler): () => void {
    const key = `${widgetId} ${action}`;
    this.actions.set(key, handler);
    return () => {
      if (this.actions.get(key) === handler) this.actions.delete(key);
    };
  }

  emit(widgetId: string, event: string, payload?: unknown): void {
    const list = this.wiring.get(`${widgetId} ${event}`) ?? [];
    for (const m of list) {
      this.actions.get(`${m.to} ${m.action}`)?.(payload);
    }
  }
}
