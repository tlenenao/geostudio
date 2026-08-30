// SPDX-License-Identifier: Apache-2.0
import { EmptyState } from "../ui/kit/EmptyState";
import { t } from "../i18n";

export function TasksComingSoonPage() {
  return <EmptyState title={t("domain.tasks")} description={t("comingSoon.tasks")} />;
}
