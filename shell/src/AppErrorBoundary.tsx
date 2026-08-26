// SPDX-License-Identifier: Apache-2.0
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

// Distinct de WidgetErrorBoundary (builder/WidgetHost.tsx), qui isole un
// widget individuel — celui-ci est au niveau racine de l'app (App.tsx) et
// attrape tout ce qui n'est PAS un widget : chrome du builder, pages,
// panneaux (I12, revue de projet 2026-08-20 — un seul ErrorBoundary
// existait, scopé par widget, donc toute exception de rendu ailleurs
// produisait un écran blanc).
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(err: unknown) {
    console.error("AppErrorBoundary: unhandled render error", err);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4 bg-slate-50 text-center">
          <p className="text-lg font-medium text-slate-800">Une erreur est survenue.</p>
          <p className="text-sm text-slate-500">
            Rechargez la page ; si le problème persiste, contactez votre administrateur.
          </p>
          <button
            type="button"
            className="rounded bg-slate-800 px-4 py-2 text-sm text-white"
            onClick={() => window.location.reload()}
          >
            Recharger
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
