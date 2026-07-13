import type { ActionMessage } from "../api/types";
import { evaluateExpression, type ExprContext } from "./expr";

export type BusHandler = (payload?: unknown) => void;

// Per-app event bus. Widgets emit events and register actions; the renderer
// wires config.messages so emitting an event invokes the target action(s).
// Keys join id + name with a space; ids are UUIDs / fixed literals (no spaces), so keys don't collide in practice.
export class ActionBus {
  private actions = new Map<string, BusHandler>();
  private wiring = new Map<string, ActionMessage[]>();
  private context: ExprContext = { vars: {}, user: { name: "" } };

  configure(messages: ActionMessage[]): void {
    this.wiring.clear();
    for (const m of messages) {
      const key = `${m.from} ${m.event}`;
      const list = this.wiring.get(key) ?? [];
      list.push(m);
      this.wiring.set(key, list);
    }
  }

  // Keeps the vars/user available to a message's `when` condition current.
  // Called by AppRenderer (Task 3) whenever live variables or the
  // authenticated user change.
  setContext(context: ExprContext): void {
    this.context = context;
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
    const record = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : undefined;
    for (const m of list) {
      if (m.when && !evaluateExpression(m.when, { ...this.context, record })) continue;
      try {
        this.actions.get(`${m.to} ${m.action}`)?.(payload);
      } catch (err) {
        console.error(`Action bus: handler for "${m.to} ${m.action}" threw`, err);
      }
    }
  }
}
