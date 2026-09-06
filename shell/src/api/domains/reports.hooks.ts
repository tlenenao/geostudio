// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { ReportSchedulePayload } from "../types";

export function useCreateReportSchedule() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; report: ReportSchedulePayload }) =>
      client.createReportScheduleItem(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useReportScheduleConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["report-schedule", pk],
    queryFn: () => client.getReportScheduleConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveReportSchedule(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReportSchedulePayload) => client.saveReportScheduleConfig(pk, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["report-schedule", pk] });
    },
  });
}
