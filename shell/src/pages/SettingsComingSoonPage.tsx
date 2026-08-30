// SPDX-License-Identifier: Apache-2.0
import { EmptyState } from "../ui/kit/EmptyState";
import { t } from "../i18n";

export function SettingsComingSoonPage() {
  return <EmptyState title={t("domain.settings")} description={t("comingSoon.settings")} />;
}
