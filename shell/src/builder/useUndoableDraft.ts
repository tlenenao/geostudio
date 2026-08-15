// SPDX-License-Identifier: Apache-2.0
// Undo/redo for the builder's edited AppConfig (SP-19). Wraps the single
// setDraft setter every panel already funnels edits through (verified
// against the real code, not assumed — cf. docs/superpowers/specs/
// 2026-08-05-undo-redo-builder-design.md §3): no other panel/widget file
// needs to change.
//
// No panel buffers text input locally (every keystroke calls onChange →
// setDraft directly, across ~20 widget PropsPanels plus PropsPanel/
// ThemePanel/VariablesPanel/ActionsPanel/NavigationPanel/DataSourcePanel).
// Pushing an undo snapshot on every call would explode the stack one entry
// per keystroke. Instead: the *first* setDraft call after the stack was
// last flushed captures the pre-burst config as the pending baseline; later
// calls within COALESCE_WINDOW_MS extend the same burst without
// re-capturing. A discrete action (one GridCanvas arrow click, one "add
// widget" click) naturally flushes on its own since nothing else calls
// setDraft within the window. undo()/redo() always flush a still-pending
// burst synchronously first, so Ctrl+Z is correct even mid-burst.
import { useCallback, useRef, useState } from "react";
import type { AppConfig } from "../api/types";
import { applyRedo, applyUndo, createUndoStack, pushUndo, type UndoStack } from "./undoStack";

const COALESCE_WINDOW_MS = 400;

export type UndoableDraft = {
  draft: AppConfig | null;
  setDraft: (update: AppConfig | null | ((prev: AppConfig | null) => AppConfig | null)) => void;
  seedDraft: (value: AppConfig) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
};

export function useUndoableDraft(): UndoableDraft {
  const [draft, setDraftState] = useState<AppConfig | null>(null);
  const stackRef = useRef<UndoStack<AppConfig>>(createUndoStack());
  const pendingBaselineRef = useRef<AppConfig | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingBaselineRef.current === null) return;
    stackRef.current = pushUndo(stackRef.current, pendingBaselineRef.current);
    pendingBaselineRef.current = null;
    setCanUndo(true);
    setCanRedo(false);
  }, []);

  const setDraft = useCallback<UndoableDraft["setDraft"]>((update) => {
    setDraftState((prev) => {
      const next = typeof update === "function"
        ? (update as (p: AppConfig | null) => AppConfig | null)(prev)
        : update;
      if (next !== prev && prev !== null) {
        if (pendingBaselineRef.current === null) pendingBaselineRef.current = prev;
        if (timerRef.current !== null) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flush, COALESCE_WINDOW_MS);
      }
      return next;
    });
  }, [flush]);

  // Seeds the initial config once loaded, bypassing history entirely — the
  // starting point of the session, not an edit. Undoing it would set draft
  // back to null and break rendering. `prev ?? value` mirrors the original
  // AppBuilderPage seeding effect (never clobbers in-flight edits on a
  // refetch).
  const seedDraft = useCallback((value: AppConfig) => {
    setDraftState((prev) => prev ?? value);
  }, []);

  const undo = useCallback(() => {
    flush();
    setDraftState((prev) => {
      if (prev === null) return prev;
      const result = applyUndo(stackRef.current, prev);
      if (result === null) return prev;
      stackRef.current = result.stack;
      setCanUndo(result.stack.past.length > 0);
      setCanRedo(true);
      return result.value;
    });
  }, [flush]);

  const redo = useCallback(() => {
    flush();
    setDraftState((prev) => {
      if (prev === null) return prev;
      const result = applyRedo(stackRef.current, prev);
      if (result === null) return prev;
      stackRef.current = result.stack;
      setCanUndo(true);
      setCanRedo(result.stack.future.length > 0);
      return result.value;
    });
  }, [flush]);

  return { draft, setDraft, seedDraft, undo, redo, canUndo, canRedo };
}
