// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useEraseUser, useMe, usePurgeStatus, useRequestTenantPurge } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

// SP-58 (spec §3.3, risque §5) : anonymisation et purge sont DEUX actions
// de nature radicalement différente (l'une limitée et réversible dans son
// effet — un compte devient vide, le tenant continue de fonctionner ;
// l'autre efface tout un tenant, irréversible) — jamais rapprochées
// visuellement au point qu'un survol ou un clic distrait puisse confondre
// l'une avec l'autre. Deux panneaux distincts, styles de danger différents,
// séparés par un espacement large et un changement de fond.

function EraseUserSection() {
  const [userId, setUserId] = useState("");
  const [result, setResult] = useState<"idle" | "success" | "error">("idle");
  const eraseUser = useEraseUser();

  async function handleErase() {
    setResult("idle");
    try {
      await eraseUser.mutateAsync(userId.trim());
      setResult("success");
      setUserId("");
    } catch {
      setResult("error");
    }
  }

  return (
    <Panel className="flex flex-col gap-3 border border-rule bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">Anonymiser un compte</h2>
      <p className="text-sm text-ink-2">
        Écrase le nom d&apos;utilisateur, l&apos;email et l&apos;identité de connexion d&apos;un
        compte. Les objets qu&apos;il possède (cartes, collections, pièces jointes) restent intacts,
        attribués au compte anonymisé. Effet limité — le tenant continue de fonctionner normalement.
      </p>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Identifiant de l&apos;utilisateur (ou « me » pour votre propre compte)
        <Input
          aria-label="Identifiant de l'utilisateur à anonymiser"
          value={userId}
          onChange={(e) => {
            setUserId(e.target.value);
            setResult("idle");
          }}
        />
      </label>
      <Button
        size="sm"
        variant="outline"
        disabled={!userId.trim() || eraseUser.isPending}
        onClick={() => void handleErase()}
      >
        Anonymiser ce compte
      </Button>
      {result === "success" && (
        <p role="status" className="text-sm text-ink-2">
          Compte anonymisé.
        </p>
      )}
      {result === "error" && (
        <p role="alert" className="text-sm text-danger">
          Échec de l&apos;anonymisation.
        </p>
      )}
    </Panel>
  );
}

function PurgeTenantSection() {
  const meQuery = useMe();
  const [confirmSlug, setConfirmSlug] = useState("");
  const [purgeId, setPurgeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestPurge = useRequestTenantPurge();
  const statusQuery = usePurgeStatus(purgeId);

  const tenantSlug = meQuery.data?.tenantSlug ?? "";
  const tenantId = meQuery.data?.tenantId ?? "";
  const slugMatches = confirmSlug.length > 0 && confirmSlug === tenantSlug;

  async function handlePurge() {
    setError(null);
    try {
      const result = await requestPurge.mutateAsync({
        tenantId,
        confirmSlug,
      });
      setPurgeId(result.jobId);
    } catch {
      setError("Échec du déclenchement de la purge.");
    }
  }

  return (
    <Panel className="flex flex-col gap-3 border-2 border-danger bg-danger/5 p-4">
      <h2 className="text-base font-semibold text-danger">Purger toutes les données du tenant</h2>
      <p className="text-sm text-ink">
        Supprime <strong>irréversiblement</strong> toutes les données de ce tenant : items,
        collections (y compris leurs tables), utilisateurs, rôles, pièces jointes, journal
        d&apos;audit — puis le tenant lui-même. Aucune restauration possible après confirmation.
      </p>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Retapez le slug du tenant (<code>{tenantSlug || "…"}</code>) pour confirmer
        <Input
          aria-label="Confirmer le slug du tenant"
          value={confirmSlug}
          onChange={(e) => setConfirmSlug(e.target.value)}
        />
      </label>
      <Button
        size="sm"
        variant="danger"
        disabled={!slugMatches || requestPurge.isPending || purgeId !== null}
        onClick={() => void handlePurge()}
      >
        Purger définitivement ce tenant
      </Button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {purgeId && statusQuery.data === null && (
        <p role="status" className="text-sm text-ink-2">
          Purge en cours…
        </p>
      )}
      {purgeId && statusQuery.data && (
        <p role="status" className="text-sm text-ink-2">
          Purge terminée à {statusQuery.data.completedAt}.
        </p>
      )}
    </Panel>
  );
}

export function ComplianceAdminPage() {
  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              <Link to="/admin/users" className="text-accent hover:underline">
                Utilisateurs →
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "compliance",
          label: "Conformité",
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Conformité (RGPD)</h1>
              <EraseUserSection />
              <PurgeTenantSection />
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>
                Deux actions distinctes : anonymiser un compte (effet limité, réversible dans ses
                conséquences pratiques) et purger tout le tenant (irréversible). Ne jamais confondre
                l&apos;une avec l&apos;autre.
              </p>
            </div>
          ),
        }}
      />
    </div>
  );
}
