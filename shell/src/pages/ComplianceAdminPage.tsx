// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useEraseUser, useMe, usePurgeStatus, useRequestTenantPurge } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

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
      <h2 className="text-base font-semibold text-ink">{t("compliance.eraseSectionTitle")}</h2>
      <p className="text-sm text-ink-2">{t("compliance.eraseDescription")}</p>
      <label className="flex flex-col gap-1 text-sm text-ink">
        {t("compliance.userIdLabel")}
        <Input
          aria-label={t("compliance.userIdAria")}
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
        {t("compliance.eraseButton")}
      </Button>
      {result === "success" && (
        <p role="status" className="text-sm text-ink-2">
          {t("compliance.eraseSuccess")}
        </p>
      )}
      {result === "error" && (
        <p role="alert" className="text-sm text-danger">
          {t("compliance.eraseError")}
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
      setError(t("compliance.purgeRequestError"));
    }
  }

  return (
    <Panel className="flex flex-col gap-3 border-2 border-danger bg-danger/5 p-4">
      <h2 className="text-base font-semibold text-danger">{t("compliance.purgeSectionTitle")}</h2>
      <p className="text-sm text-ink">
        {t("compliance.purgeWarningBefore")} <strong>{t("compliance.purgeWarningEmphasis")}</strong>{" "}
        {t("compliance.purgeWarningAfter")}
      </p>
      <label className="flex flex-col gap-1 text-sm text-ink">
        {t("compliance.confirmSlugBefore")}
        <code>{tenantSlug || "…"}</code>
        {t("compliance.confirmSlugAfter")}
        <Input
          aria-label={t("compliance.confirmSlugAria")}
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
        {t("compliance.purgeButton")}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {purgeId && statusQuery.data === null && (
        <p role="status" className="text-sm text-ink-2">
          {t("compliance.purgeInProgress")}
        </p>
      )}
      {purgeId && statusQuery.data && (
        <p role="status" className="text-sm text-ink-2">
          {t("compliance.purgeCompleted", { completedAt: statusQuery.data.completedAt })}
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
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
              <Link to="/admin/users" className="text-accent hover:underline">
                {t("extensions.linkUsers")}
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "compliance",
          label: t("compliance.title"),
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">{t("compliance.heading")}</h1>
              <EraseUserSection />
              <PurgeTenantSection />
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("compliance.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("compliance.helpText")}</p>
            </div>
          ),
        }}
      />
    </div>
  );
}
