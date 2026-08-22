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
//
// All ref bookkeeping (stackRef/pendingBaselineRef/timerRef/draftRef) happens
// in the outer function bodies below, never inside a function passed to
// setDraftState — React (and specifically <StrictMode>, which wraps the
// whole app in dev, see main.tsx) may invoke a useState updater function
// twice to surface impurities. Mutating refs inside one would double the
// mutation on every call in dev, corrupting the stack (SP-19 final-branch-
// review fix pass, finding C1). `draftRef` mirrors `draft` synchronously
// (updated at call time, not on commit) so every one of setDraft/seedDraft/
// undo/redo can compute its next value from a reliable "current" value
// without going through setDraftState's updater form at all — setDraftState
// is only ever called with a plain, already-computed value.
import { useCallback, useEffect, useRef, useState } from "react";
import type { AppConfig } from "../api/types";
import { applyRedo, applyUndo, createUndoStack, pushUndo, type UndoStack } from "./undoStack";

const COALESCE_WINDOW_MS = 400;

export type UndoableDraft = {
  draft: AppConfig | null;
  setDraft: (update: AppConfig | null | ((prev: AppConfig | null) => AppConfig | null)) => void;
  seedDraft: (value: AppConfig) => void;
  resetDraft: (value: AppConfig) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
};

export function useUndoableDraft(): UndoableDraft {
  const [draft, setDraftState] = useState<AppConfig | null>(null);
  const draftRef = useRef<AppConfig | null>(null);
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

  // Clears a still-pending coalesce timer on unmount. Without this, navigating
  // away from the builder mid-burst leaves the timer armed and flush() (via
  // setCanUndo/setCanRedo) fires against an unmounted hook instance (SP-19
  // final-branch-review fix pass, finding I1).
  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    },
    [],
  );

  const setDraft = useCallback<UndoableDraft["setDraft"]>(
    (update) => {
      const prev = draftRef.current;
      const next =
        typeof update === "function"
          ? (update as (p: AppConfig | null) => AppConfig | null)(prev)
          : update;
      if (next !== prev && prev !== null) {
        if (pendingBaselineRef.current === null) pendingBaselineRef.current = prev;
        if (timerRef.current !== null) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flush, COALESCE_WINDOW_MS);
      }
      draftRef.current = next;
      setDraftState(next);
    },
    [flush],
  );

  // Seeds the initial config once loaded, bypassing history entirely — the
  // starting point of the session, not an edit. Undoing it would set draft
  // back to null and break rendering. Reading/checking draftRef.current
  // directly (instead of `prev ?? value` inside a setState updater) mirrors
  // the original AppBuilderPage seeding effect (never clobbers in-flight
  // edits on a refetch).
  const seedDraft = useCallback((value: AppConfig) => {
    if (draftRef.current !== null) return;
    draftRef.current = value;
    setDraftState(value);
  }, []);

  // Remplace le brouillon par une valeur qui vient du SERVEUR (restauration
  // d'une version antérieure, SP-23) et vide l'historique. La pile ne peut
  // pas défaire une écriture serveur : la laisser pleine ferait croire à
  // l'auteur qu'un Ctrl+Z annule la restauration, alors qu'il ne toucherait
  // que son brouillon local pendant que le serveur porte déjà la version
  // N+1. Tout le bookkeeping se fait ici, jamais dans un updater passé à
  // setDraftState (<StrictMode> l'invoquerait deux fois — SP-19, C1).
  const resetDraft = useCallback((value: AppConfig) => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingBaselineRef.current = null;
    stackRef.current = createUndoStack();
    draftRef.current = value;
    setCanUndo(false);
    setCanRedo(false);
    setDraftState(value);
  }, []);

  const undo = useCallback(() => {
    flush();
    const prev = draftRef.current;
    if (prev === null) return;
    const result = applyUndo(stackRef.current, prev);
    if (result === null) return;
    stackRef.current = result.stack;
    draftRef.current = result.value;
    setCanUndo(result.stack.past.length > 0);
    setCanRedo(true);
    setDraftState(result.value);
  }, [flush]);

  const redo = useCallback(() => {
    flush();
    const prev = draftRef.current;
    if (prev === null) return;
    const result = applyRedo(stackRef.current, prev);
    if (result === null) return;
    stackRef.current = result.stack;
    draftRef.current = result.value;
    setCanUndo(true);
    setCanRedo(result.stack.future.length > 0);
    setDraftState(result.value);
  }, [flush]);

  return { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo };
}
