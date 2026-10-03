// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMe, useNotificationPreference, useUpdateNotificationPreference } from "../api/hooks";
import type { NotificationPreferenceValue } from "../api/types";
import { roleLabel } from "../auth/roleLabel";
import { useConfig } from "../ConfigContext";
import { Badge } from "../ui/kit/Badge";
import { Radio } from "../ui/kit/Radio";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import { readThemePreference, saveThemePreference, type ThemePreference } from "../lib/theme";
import { LoadingState } from "../ui/kit/LoadingState";
import { PageTitle } from "../ui/kit/PageTitle";

function ProfileSection() {
  const meQuery = useMe();
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.profileTitle")}</h2>
      {meQuery.isLoading && <LoadingState />}
      {meQuery.data && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm text-ink-2">
          <dt>{t("settings.profileUsername")}</dt>
          <dd>{meQuery.data.username}</dd>
          <dt>{t("settings.profileEmail")}</dt>
          <dd>{meQuery.data.email ?? "—"}</dd>
          <dt>{t("settings.profileName")}</dt>
          <dd>
            {[meQuery.data.firstName, meQuery.data.lastName].filter(Boolean).join(" ") || "—"}
          </dd>
          <dt>{t("settings.profileRole")}</dt>
          <dd>
            <Badge>{roleLabel(meQuery.data)}</Badge>
          </dd>
          <dt>{t("settings.profileTenant")}</dt>
          <dd>{meQuery.data.tenantSlug}</dd>
        </dl>
      )}
    </section>
  );
}

function NotificationsSection() {
  const preferenceQuery = useNotificationPreference();
  const updatePreference = useUpdateNotificationPreference();
  const [saveError, setSaveError] = useState(false);

  async function handleChange(value: NotificationPreferenceValue) {
    setSaveError(false);
    try {
      await updatePreference.mutateAsync(value);
    } catch {
      setSaveError(true);
    }
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.notificationsTitle")}</h2>
      {preferenceQuery.isLoading && <LoadingState />}
      {preferenceQuery.data && (
        <Radio.Group
          aria-label={t("settings.notificationsTitle")}
          value={preferenceQuery.data}
          disabled={updatePreference.isPending}
          onValueChange={(value) => void handleChange(value as NotificationPreferenceValue)}
        >
          <Radio.Item value="all">{t("settings.notificationsAll")}</Radio.Item>
          <Radio.Item value="failuresOnly">{t("settings.notificationsFailuresOnly")}</Radio.Item>
          <Radio.Item value="none">{t("settings.notificationsNone")}</Radio.Item>
        </Radio.Group>
      )}
      {saveError && (
        <p role="alert" className="text-sm text-danger">
          {t("settings.notificationsSaveError")}
        </p>
      )}
    </section>
  );
}

function AppearanceSection() {
  const [theme, setTheme] = useState<ThemePreference>(readThemePreference);
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.appearanceTitle")}</h2>
      <Radio.Group
        aria-label={t("settings.appearanceTitle")}
        value={theme}
        onValueChange={(value) => {
          setTheme(value as ThemePreference);
          saveThemePreference(value as ThemePreference);
        }}
      >
        <Radio.Item value="auto">{t("settings.appearanceAuto")}</Radio.Item>
        <Radio.Item value="light">{t("settings.appearanceLight")}</Radio.Item>
        <Radio.Item value="dark">{t("settings.appearanceDark")}</Radio.Item>
      </Radio.Group>
    </section>
  );
}

function AccountSection() {
  const config = useConfig();
  if (config.authMode === "mock") return null;
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.accountTitle")}</h2>
      <a
        href={`${config.oidcAuthority}/account`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent hover:underline"
      >
        {t("settings.accountKeycloakLink")}
      </a>
    </section>
  );
}

export function SettingsPage() {
  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "settings",
          label: t("domain.settings"),
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <PageTitle>{t("settings.heading")}</PageTitle>
              <ProfileSection />
              <NotificationsSection />
              <AppearanceSection />
              <AccountSection />
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("settings.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("settings.helpText")}</p>
            </div>
          ),
        }}
      />
    </div>
  );
}
