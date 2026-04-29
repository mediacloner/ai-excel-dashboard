import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as api from "@/lib/api"

export function useDashboards(spaceId: string | undefined) {
  return useQuery({
    queryKey: ["dashboards", spaceId],
    queryFn: () => api.listDashboards(spaceId!),
    enabled: !!spaceId,
  })
}

export function useDashboard(id: string | undefined) {
  return useQuery({
    queryKey: ["dashboard", id],
    queryFn: () => api.getDashboard(id!),
    enabled: !!id,
  })
}

export function useCreateDashboard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ spaceId, name }: { spaceId: string; name: string }) =>
      api.createDashboard(spaceId, name),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["dashboards", vars.spaceId] }),
  })
}

export function useDeleteWidget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteWidget(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  })
}

export function useWidgetVersions(widgetId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["widget-versions", widgetId],
    queryFn: () => api.listWidgetVersions(widgetId!),
    enabled: !!widgetId && enabled,
  })
}

export function useRestoreWidgetVersion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (versionId: string) => api.restoreWidgetVersion(versionId),
    onSuccess: async (widget) => {
      // Force an immediate refetch so the dashboard hook returns fresh data
      // and space.tsx's useEffect pushes the restored widget into the store.
      await qc.invalidateQueries({ queryKey: ["dashboard", widget.dashboard_id] })
      await qc.refetchQueries({ queryKey: ["dashboard", widget.dashboard_id] })
      qc.invalidateQueries({ queryKey: ["widget-versions", widget.id] })
    },
  })
}
